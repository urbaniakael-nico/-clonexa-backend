"""MODO CONSTRUCTOR (fase 1) y BIBLIOTECA 3D: SOLO consola v2+ (sesion de Admin V2). Ningun cliente ve el constructor.

Paginas (sin sesion: al ingreso) y archivos (401 sin sesion):
- GET /admin-v2plus/constructor?empresa=<id>     el constructor (plano 2D + vista 3D en vivo + propiedades).
- GET /admin-v2plus/constructor/vista            vista 3D del borrador (iframe del constructor; motor de la oficina).
- GET /admin-v2plus/biblioteca                   Biblioteca: fuentes, subir, Poly Haven, revision y "Créditos 3D".
API (GUARD: 401 sin sesion antes de leer el cuerpo). Todo cerrado por company_id:
- GET  /admin-v2/api/constructor/empresas/{id}                 borrador (se crea con la plantilla de su piso + lo que
                                                               tenia "Editar distribución"), version publicada, historial,
                                                               entidades reales, avisos, interruptores y paleta de marca.
- PUT  .../empresas/{id}/borrador                              autoguardado (validacion estricta).
- POST .../empresas/{id}/publicar {encender?}                  crea la version publicada (y si se pide, enciende el plano
                                                               en vivo SOLO para esa empresa).
- POST .../empresas/{id}/restaurar {version}                   copia una version publicada al borrador.
- GET  .../empresas/{id}/versiones/{n}                         un plano del historial.
- POST .../empresas/{id}/plantilla {plantilla}                 el borrador pasa a ser una plantilla (Bar, Restaurante...).
- GET  .../empresas/{id}/exportar[?version=n]                  descarga .clonexa.json.
- POST .../empresas/{id}/importar                              .clonexa.json -> borrador (sin conexiones).
- PUT  .../empresas/{id}/ajustes {usa_plano?, estilo_escena?}  interruptores de la empresa (con auditoria).
- GET  /admin-v2/api/constructor/catalogo[?todos=1]            catalogo (publicados; todos = biblioteca).
- GET  /admin-v2/api/oficina/catalogo/{id}.glb|{id}.webp       archivo del catalogo (bucket privado o repo).
- POST /admin-v2/api/constructor/biblioteca/subir              subir modelo (multipart, 50 MB, formulario obligatorio).
- POST /admin-v2/api/constructor/biblioteca/revision/{id}/{aprobar|rechazar}
- GET  /admin-v2/api/constructor/biblioteca/polyhaven?q=       buscador Poly Haven (API publica, CC0).
- POST /admin-v2/api/constructor/biblioteca/polyhaven/{asset}  importar al mismo flujo.
- GET  /admin-v2/api/oficina/pisos/{id}/plano[?borrador=1]     plano para el motor 3D (publicado; borrador = constructor).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import constructor_biblioteca as cb
from app.services import constructor_plano as cp
from app.services import live3d as l3
from app.services import oficina_data as od
from app.web import admin_v2_routes as v2
from app.web import oficina_routes as ofr
from app.web.admin_v2plus_companies import GUARD, _audit, _json

router = APIRouter()
API = "/admin-v2/api/constructor"
ACTOR = "admin_v2"
PAGES = {"constructor": "oficina/constructor.html", "vista": "oficina/constructor_vista.html", "biblioteca": "oficina/biblioteca.html"}
GLB_TYPE = "model/gltf-binary"


def _err(error: Exception, status: int = 422) -> HTTPException:
    return HTTPException(status_code=status, detail=str(error))


async def _page(request: Request, db: AsyncSession, key: str) -> Response:
    if not await v2._active_session(request, db):
        return v2._no_store(RedirectResponse(url="/admin-v2plus/login", status_code=303))
    html = (ofr.WEB / PAGES[key]).read_text(encoding="utf-8")
    csp = ofr.page_csp(html)
    if key == "biblioteca":   # miniaturas del buscador de Poly Haven (solo imagenes de su CDN)
        csp = csp.replace("img-src 'self' data: blob:", "img-src 'self' data: blob: https://cdn.polyhaven.com")
    return v2._no_store(Response(html, media_type="text/html; charset=utf-8", headers={"Content-Security-Policy": csp}))


@router.get("/admin-v2plus/constructor", include_in_schema=False)
async def constructor_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _page(request, db, "constructor")


@router.get("/admin-v2plus/constructor/vista", include_in_schema=False)
async def vista_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _page(request, db, "vista")


@router.get("/admin-v2plus/creditos-3d", include_in_schema=False)
async def creditos_page(request: Request, db: AsyncSession = Depends(get_db)):
    if not await v2._active_session(request, db):
        return v2._no_store(RedirectResponse(url="/admin-v2plus/login", status_code=303))
    return v2._no_store(RedirectResponse(url="/admin-v2plus/biblioteca#creditos", status_code=303))


@router.get("/admin-v2plus/biblioteca", include_in_schema=False)
async def biblioteca_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _page(request, db, "biblioteca")


# ------------------------------------------------------------------ empresa + borrador
async def _company(db: AsyncSession, company_id: str) -> dict:
    return await ofr._company(db, company_id)


async def _assets(db: AsyncSession) -> tuple[list[dict], set[str]]:
    items = await cb.catalog(db)
    return items, {x["id"] for x in items}


async def _ensure_draft(db: AsyncSession, c: dict) -> dict:
    found = await cp.draft(db, c["id"])
    if found:
        return found
    pub = await cp.published(db, c["id"])
    if pub:
        plan = pub["plano"]
    else:
        row = await od.floor_row(db, c["id"])
        tables = await ofr._tables(db, c["id"])
        plan = cp.first_draft(ofr._template(c, row), tables, ofr._dist(row.get("distribucion")))
    await cp.save_draft(db, c["id"], plan, ACTOR)
    return await cp.draft(db, c["id"])


async def _brand(db: AsyncSession, c: dict) -> dict:
    from app.services import oficina_vivo as ov

    try:
        b = await ov.brand(db, c["id"], c.get("settings"))
    except Exception:
        await db.rollback()
        b = {}
    return b if isinstance(b, dict) else {}


async def _settings(db: AsyncSession, cid: str) -> dict:
    try:
        r = (await db.execute(text("SELECT usa_plano, estilo_escena FROM oficina_pisos WHERE company_id = CAST(:c AS uuid)"), {"c": cid})).mappings().first()
    except Exception:
        await db.rollback()
        r = None
    return {"usa_plano": bool(r and r["usa_plano"]), "estilo_escena": (r and r["estilo_escena"] in cp.SCENE_STYLES and r["estilo_escena"]) or "humano"}


async def _state(db: AsyncSession, c: dict) -> dict:
    d = await _ensure_draft(db, c)
    items, _ = await _assets(db)
    ents = await cp.entities(db, c["id"])
    pub = await cp.published(db, c["id"])
    return {"ok": True, "company": {"id": c["id"], "name": c["name"]}, "draft": {"version": d["version"], "plano": d["plano"], "hash": cp.plan_hash(d["plano"]),
            "updated_at": d["updated_at"].isoformat() if d.get("updated_at") else None},
            "published": {"version": pub["version"]} if pub else None, "history": await cp.history(db, c["id"]),
            "entities": ents, "warnings": cp.warnings(d["plano"], cb.sizes(items), ents), **(await _settings(db, c["id"])),
            "brand": await _brand(db, c), "options": _options()}


def _options() -> dict:
    return {"templates": [{"key": k, "label": cp.TEMPLATE_LABEL[k]} for k in cp.TEMPLATES],
            "walls": [{"key": k, "label": cp.WALL_LABEL[k]} for k in cp.WALL_MATERIALS],
            "floors": [{"key": k, "label": cp.FLOOR_LABEL[k]} for k in cp.FLOOR_MATERIALS],
            "openings": [{"key": k, "label": cp.OPENING_LABEL[k], "door": k in cp.DOORS, "size": cp.OPENING_SIZE[k]} for k in cp.OPENINGS],
            "zones": [{"key": k, "label": cp.ZONE_LABEL[k]} for k in cp.ZONE_KINDS],
            "screens": [{"key": k, "label": v} for k, v in cp.SCREENS.items()],
            "styles": [{"key": "humano", "label": "Humano (realista)"}, {"key": "caricatura", "label": "Caricatura (animado)"}],
            "categories": [{"key": k, "label": cb.CATEGORY_LABEL[k]} for k in cb.CATEGORIES]}


@router.get(API + "/empresas/{company_id}", include_in_schema=False, dependencies=GUARD)
async def empresa(company_id: str, db: AsyncSession = Depends(get_db)):
    return _json(await _state(db, await _company(db, company_id)))


async def _body(request: Request) -> Any:
    try:
        return await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Datos no válidos.") from None


@router.put(API + "/empresas/{company_id}/borrador", include_in_schema=False, dependencies=GUARD)
async def autoguardar(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    body = await _body(request)
    items, assets = await _assets(db)
    try:
        plan = cp.clean_plan(body.get("plano") if isinstance(body, dict) else None, assets)
    except cp.Rejected as error:
        raise _err(error) from None
    saved = await cp.save_draft(db, c["id"], plan, ACTOR)
    ents = await cp.entities(db, c["id"])
    return _json({"ok": True, **saved, "warnings": cp.warnings(plan, cb.sizes(items), ents)})


@router.post(API + "/empresas/{company_id}/publicar", include_in_schema=False, dependencies=GUARD)
async def publicar(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    body = await _body(request)
    d = await cp.draft(db, c["id"])
    if not d:
        raise HTTPException(status_code=409, detail="No hay borrador para publicar.")
    _, assets = await _assets(db)
    try:
        plan = cp.clean_plan(d["plano"], assets)
    except cp.Rejected as error:
        raise _err(error) from None
    version = await cp.publish(db, c["id"], plan, ACTOR, str((body or {}).get("nota") or ""))
    if isinstance(body, dict) and body.get("encender") is True:
        await cp.set_uses_plan(db, c["id"], True, ACTOR)
    _drop(c["id"])
    await _audit(request, constructor_publica=c["id"], version=version, encender="si" if (body or {}).get("encender") is True else "no")
    return _json({"ok": True, "version": version, **(await _settings(db, c["id"])), "history": await cp.history(db, c["id"])})


def _drop(cid: str) -> None:
    ofr.reset_db_cache()
    l3.drop_live(cid)
    l3.forget(cid)


@router.post(API + "/empresas/{company_id}/restaurar", include_in_schema=False, dependencies=GUARD)
async def restaurar(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    body = await _body(request)
    try:
        v = int((body or {}).get("version"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Versión no válida.") from None
    plan = await cp.version_plan(db, c["id"], v)
    if plan is None:
        raise HTTPException(status_code=404, detail="Esa versión no existe.")
    await cp.save_draft(db, c["id"], plan, ACTOR)
    await _audit(request, constructor_restaura=c["id"], version=v)
    return _json(await _state(db, c))


@router.get(API + "/empresas/{company_id}/versiones/{version}", include_in_schema=False, dependencies=GUARD)
async def version(company_id: str, version: int, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    plan = await cp.version_plan(db, c["id"], version)
    if plan is None:
        raise HTTPException(status_code=404, detail="Esa versión no existe.")
    return _json({"ok": True, "version": version, "plano": plan})


@router.post(API + "/empresas/{company_id}/plantilla", include_in_schema=False, dependencies=GUARD)
async def plantilla(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    body = await _body(request)
    try:
        plan = cp.template(str((body or {}).get("plantilla") or ""), await ofr._tables(db, c["id"]))
    except cp.Rejected as error:
        raise _err(error) from None
    await cp.save_draft(db, c["id"], plan, ACTOR)
    return _json(await _state(db, c))


@router.get(API + "/empresas/{company_id}/exportar", include_in_schema=False, dependencies=GUARD)
async def exportar(company_id: str, version: Optional[int] = Query(None), db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    if version is not None:
        plan = await cp.version_plan(db, c["id"], version)
        if plan is None:
            raise HTTPException(status_code=404, detail="Esa versión no existe.")
    else:
        plan = (await _ensure_draft(db, c))["plano"]
    doc = cp.export_doc(plan, c["name"], version)
    slug = re.sub(r"[^a-z0-9]+", "-", c["name"].lower()).strip("-")[:40] or "plano"
    return v2._no_store(Response(json.dumps(doc, ensure_ascii=False, indent=1), media_type="application/json",
                                 headers={"Content-Disposition": f'attachment; filename="{slug}.clonexa.json"'}))


@router.post(API + "/empresas/{company_id}/importar", include_in_schema=False, dependencies=GUARD)
async def importar(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    if int(request.headers.get("content-length") or 0) > cp.MAX_BYTES * 2:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande.")
    raw = await request.body()
    _, assets = await _assets(db)
    try:
        plan = cp.import_doc(raw, assets)
    except cp.Rejected as error:
        raise _err(error) from None
    await cp.save_draft(db, c["id"], plan, ACTOR)
    await _audit(request, constructor_importa=c["id"], objetos=len(plan["objetos"]))
    return _json(await _state(db, c))


@router.put(API + "/empresas/{company_id}/ajustes", include_in_schema=False, dependencies=GUARD)
async def ajustes(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    body = await _body(request)
    if not isinstance(body, dict) or not body:
        raise HTTPException(status_code=422, detail="Nada que guardar.")
    if "usa_plano" in body:
        if not isinstance(body["usa_plano"], bool):
            raise HTTPException(status_code=422, detail="Interruptor no válido.")
        if body["usa_plano"] and not await cp.published(db, c["id"]):
            raise HTTPException(status_code=409, detail="Primero publica una versión del plano.")
        await cp.set_uses_plan(db, c["id"], body["usa_plano"], ACTOR)
    if "estilo_escena" in body:
        if body["estilo_escena"] not in cp.SCENE_STYLES:
            raise HTTPException(status_code=422, detail="Estilo no válido.")
        await db.execute(text("""INSERT INTO oficina_pisos (company_id, estilo_escena, updated_by) VALUES (CAST(:c AS uuid), :e, :a)
            ON CONFLICT (company_id) DO UPDATE SET estilo_escena = EXCLUDED.estilo_escena, updated_by = EXCLUDED.updated_by, updated_at = now()"""),
                         {"c": c["id"], "e": body["estilo_escena"], "a": ACTOR})
        await db.commit()
    _drop(c["id"])
    await _audit(request, constructor_ajustes=c["id"], **{k: str(v) for k, v in body.items() if k in ("usa_plano", "estilo_escena")})
    return _json({"ok": True, **(await _settings(db, c["id"]))})


# ------------------------------------------------------------------ catalogo y archivos
def _public_item(x: dict, base: str) -> dict:
    out = {k: x.get(k) for k in ("id", "nombre", "categoria", "zonas", "origen", "forma", "medidas", "variantes", "conectable", "capa", "icono",
                                  "licencia", "fuente", "autor", "atribucion", "estado", "bytes", "poligonos", "notas", "created_at")}
    if x.get("origen") == "recurso" and x.get("archivo"):
        meta = ofr.manifest().get("files", {}).get(x["archivo"]) or {}
        out["url"] = f"{base}recursos/{x['archivo']}?v={str(meta.get('sha', ''))[:12]}"
        out["bytes"] = int(meta.get("bytes") or 0)
    elif x.get("origen") == "bucket" and x.get("archivo"):
        tag = hashlib.sha256(str(x["archivo"]).encode()).hexdigest()[:10]
        out["url"] = f"{base}api/catalogo/{x['id']}.glb?v={tag}"
        out["mini"] = f"{base}api/catalogo/{x['id']}.webp?v={tag}"
    return out


CONSOLE_BASE = "/admin-v2plus/oficina/"


def console_items(items: list[dict]) -> list[dict]:
    out = []
    for x in items:
        it = _public_item(x, CONSOLE_BASE)
        for k in ("url", "mini"):
            if it.get(k, "").startswith(CONSOLE_BASE + "api/"):
                it[k] = it[k].replace(CONSOLE_BASE + "api/", "/admin-v2/api/oficina/")
        out.append(it)
    return out


@router.get(API + "/catalogo", include_in_schema=False, dependencies=GUARD)
async def catalogo(todos: int = Query(0), db: AsyncSession = Depends(get_db)):
    items = await cb.catalog(db, cb.STATES if todos else ("publicado",))
    pub = [x for x in items if x["estado"] == "publicado"]
    return _json({"ok": True, "items": console_items(items), "stats": cb.stats(pub),
                  "categories": [{"key": k, "label": cb.CATEGORY_LABEL[k]} for k in cb.CATEGORIES]})


async def serve_item_file(db: AsyncSession, item_id: str, ext: str, allowed: Optional[set[str]] = None) -> Response:
    if not re.match(r"^[a-z0-9_-]{2,60}$", item_id) or ext not in ("glb", "webp"):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    if allowed is not None and item_id not in allowed:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    it = await cb.item(db, item_id)
    if not it or it.get("origen") != "bucket":
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    if allowed is not None and it.get("estado") != "publicado":
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    key = it.get("archivo") if ext == "glb" else it.get("miniatura")
    try:
        raw = await asyncio.to_thread(cb.get, key)
    except Exception:
        raise HTTPException(status_code=503, detail="El almacenamiento no responde.", headers={"Cache-Control": "no-store"}) from None
    return Response(raw, media_type=GLB_TYPE if ext == "glb" else "image/webp",
                    headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.get("/admin-v2/api/oficina/catalogo/{name}", include_in_schema=False, dependencies=GUARD)
async def catalogo_archivo(name: str, db: AsyncSession = Depends(get_db)):
    item_id, _, ext = name.rpartition(".")
    return await serve_item_file(db, item_id, ext)


# ------------------------------------------------------------------ plano para el motor 3D
async def engine_payload(db: AsyncSession, cid: str, plan: dict, version: Optional[int], base: str, settings: dict) -> dict:
    items = await cb.catalog(db)
    used = {o["asset"] for o in plan.get("objetos", [])}
    cat = [_public_item(x, base) for x in items if x["id"] in used]
    return {"ok": True, "version": version, "plano": cp.for_engine(plan), "estilo": settings["estilo_escena"], "catalogo": cat}


@router.get("/admin-v2/api/oficina/pisos/{company_id}/plano", include_in_schema=False, dependencies=GUARD)
async def plano_motor(company_id: str, borrador: int = Query(0), db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    st = await _settings(db, c["id"])
    if borrador:
        d = await _ensure_draft(db, c)
        plan, ver = d["plano"], d["version"]
    else:
        live = await cp.live_plan(db, c["id"])
        if not live:
            raise HTTPException(status_code=404, detail="Esta empresa no tiene plano publicado en vivo.")
        plan, ver = live["plano"], live["version"]
    out = await engine_payload(db, c["id"], plan, ver, CONSOLE_BASE, st)
    out["catalogo"] = console_items([x for x in await cb.catalog(db) if x["id"] in {o["asset"] for o in plan["objetos"]}])
    out.update(name=c["name"], brand=await _brand(db, c))
    return _json(out)


# ------------------------------------------------------------------ biblioteca: subir, revisar, Poly Haven
@router.post(API + "/biblioteca/subir", include_in_schema=False, dependencies=GUARD)
async def subir(request: Request, db: AsyncSession = Depends(get_db)):
    if int(request.headers.get("content-length") or 0) > cb.MAX_UPLOAD + 1024 * 1024:
        raise HTTPException(status_code=413, detail="El archivo pasa de 50 MB.")
    form = await request.form()
    up = form.get("archivo")
    if up is None or not hasattr(up, "read"):
        raise HTTPException(status_code=422, detail="Elige el archivo del modelo.")
    try:
        fields = cb.clean_form({k: form.get(k) for k in ("nombre", "categoria", "conectable", "licencia", "fuente", "autor", "atribucion", "alto", "ancho")}
                               | {"zonas": form.getlist("zonas") if hasattr(form, "getlist") else form.get("zonas")})
    except cb.Rejected as error:
        raise _err(error) from None
    raw = await up.read(cb.MAX_UPLOAD + 1)
    if len(raw) > cb.MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="El archivo pasa de 50 MB.")
    try:
        prep = await asyncio.to_thread(cb.convert, str(getattr(up, "filename", "") or "modelo"), raw, fields["alto"], fields["ancho"])
    except cb.Rejected as error:
        raise _err(error) from None
    try:
        saved = await cb.store(db, fields, prep, hashlib.sha256(raw).hexdigest(), ACTOR)
    except Exception as error:
        if type(error).__name__ == "StorageUnavailable":
            raise HTTPException(status_code=503, detail=str(error)) from None
        raise
    await _audit(request, biblioteca_sube=saved["id"], estado=saved["estado"], licencia=fields["licencia_clave"])
    return _json({"ok": True, **saved})


@router.post(API + "/biblioteca/revision/{item_id}/{accion}", include_in_schema=False, dependencies=GUARD)
async def revisar(item_id: str, accion: str, request: Request, db: AsyncSession = Depends(get_db)):
    state = {"aprobar": "publicado", "rechazar": "rechazado"}.get(accion)
    if not state or not re.match(r"^[a-z0-9_-]{2,60}$", item_id):
        raise HTTPException(status_code=404, detail="No encontrado.")
    try:
        ok = await cb.set_state(db, item_id, state, ACTOR)
    except cb.Rejected as error:
        raise _err(error) from None
    if not ok:
        raise HTTPException(status_code=404, detail="Ese objeto no está en revisión.")
    await _audit(request, biblioteca=item_id, accion=accion)
    return _json({"ok": True, "id": item_id, "estado": state})


@router.get(API + "/biblioteca/polyhaven", include_in_schema=False, dependencies=GUARD)
async def polyhaven(q: str = Query("", max_length=60)):
    try:
        return _json({"ok": True, "items": await cb.polyhaven_search(q)})
    except Exception:
        raise HTTPException(status_code=502, detail="Poly Haven no responde ahora. Intenta en un momento.") from None


@router.post(API + "/biblioteca/polyhaven/{asset_id}", include_in_schema=False, dependencies=GUARD)
async def polyhaven_importar(asset_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Datos no válidos.")
    try:
        gltf, files, _base, meta = await cb.polyhaven_fetch(asset_id)
        fields = cb.clean_form({**body, "licencia": "cc0", "fuente": meta["fuente"], "autor": meta["autor"], "nombre": body.get("nombre") or meta["nombre"]})
        prep = await asyncio.to_thread(cb.convert_gltf, gltf, files, fields["alto"], fields["ancho"])
    except cb.Rejected as error:
        raise _err(error) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="No se pudo descargar el modelo de Poly Haven.") from None
    saved = await cb.store(db, fields, prep, hashlib.sha256(gltf).hexdigest(), ACTOR)
    await _audit(request, biblioteca_polyhaven=asset_id, id=saved["id"])
    return _json({"ok": True, **saved})
