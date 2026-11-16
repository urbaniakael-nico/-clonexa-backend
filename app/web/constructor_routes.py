"""BIBLIOTECA 3D (Modo constructor + Personajes, prototipo aprobado): SOLO consola v2+ (sesión de Admin V2).

Páginas (sin sesión: al ingreso):
- GET /admin-v2plus/biblioteca3d/                 inicio: empresa, estilo, Estudio de marca y entradas.
- GET /admin-v2plus/biblioteca3d/constructor      Modo constructor (?empresa=<id>, ?lib=1 catálogo, ?lib=up subir modelo).
- GET /admin-v2plus/biblioteca3d/personajes       equipo + editor de personajes + uniformes (?empresa=<id>&id=<persona>).
- Las rutas viejas (/admin-v2plus/constructor, /constructor/vista, /biblioteca, /creditos-3d) redirigen a las nuevas.
- GET /admin-v2plus/oficina/b3d/<archivo>         módulos del prototipo (lista blanca, 401 sin sesión).
API /admin-v2/api/b3d (GUARD: 401 sin sesión antes de leer el cuerpo). Todo cerrado por company_id:
- GET  /empresas                                  empresas registradas con su Estudio de marca.
- GET  /empresas/{id}                             estilo, diseños (borradores), equipo, uniformes, entidades reales, catálogo.
- PUT  /empresas/{id}/estilo {style}              Humano / Caricatura de la empresa.
- PUT  /empresas/{id}/disenos/{d} {name, plan, thumb?}   autoguardado (validación estricta; miniatura al bucket privado).
- DELETE /empresas/{id}/disenos/{d}               borrar un diseño (si estaba en vivo, la empresa vuelve a su piso).
- POST /empresas/{id}/disenos/{d}/publicar        versión publicada + en vivo para ESA empresa.
- GET  /empresas/{id}/disenos/{d}/versiones[/{n}] historial y un plano del historial (restaurar).
- GET  /empresas/{id}/disenos/{d}/miniatura.jpg   miniatura del diseño.
- POST /empresas/{id}/importar                    .clonexa.json validado en el servidor (sin conexiones ni personas).
- PUT  /empresas/{id}/equipo/{pid}                personaje de una persona (oficina_personajes, sin duplicar).
- PUT  /empresas/{id}/uniformes {items}           uniformes de la empresa.
- POST /empresas/{id}/aplicar-marca               "Aplicar Estudio de marca a todo" (borradores, uniformes y equipo).
- POST /biblioteca/subir                          subir modelo (GLB/FBX/OBJ/ZIP, se convierte en el servidor) -> revisión.
- POST /biblioteca/{item}/{aprobar|rechazar}      revisión (los aprobados entran al catálogo en su carpeta).
- GET  /admin-v2/api/oficina/catalogo/{id}.glb|webp   archivo de un modelo (bucket privado).
- GET  /admin-v2/api/oficina/pisos/{id}/plano     plano PUBLICADO en vivo para el motor 3D de la oficina.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import constructor_biblioteca as cb
from app.services import constructor_v2 as c2
from app.services import live3d as l3
from app.services import oficina_data as od
from app.web import admin_v2_routes as v2
from app.web import oficina_routes as ofr
from app.web.admin_v2plus_companies import GUARD, _audit, _json

router = APIRouter()
API = "/admin-v2/api/b3d"
ACTOR = "admin_v2"
HOME = "/admin-v2plus/biblioteca3d/"
PAGES = {"index": "oficina/b3d/index.html", "constructor": "oficina/b3d/constructor.html", "personajes": "oficina/b3d/personajes.html"}
JS = "application/javascript"
FILES = {"core.js": JS, "store.js": JS, "catalog.js": JS, "room.js": JS, "char.js": JS, "templates.js": JS, "team.js": JS,
         "editor.js": JS, "people.js": JS, "home.js": JS, "app.css": "text/css"}
# lo que puede pedir el motor en vivo (también el visor del cliente): nunca el guardado de la consola
ENGINE_FILES = ("core.js", "catalog.js", "room.js", "char.js")
GLB_TYPE = "model/gltf-binary"
DID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
THUMB_PREFIX = "constructor/miniaturas/"


def page_csp(html: str) -> str:
    """CSP de la oficina + estilos en línea (el prototipo pinta colores con style="" en el HTML que genera)."""
    return ofr.page_csp(html).replace("style-src 'self'", "style-src 'self' 'unsafe-inline'")


async def _page(request: Request, db: AsyncSession, key: str) -> Response:
    if not await v2._active_session(request, db):
        return v2._no_store(RedirectResponse(url="/admin-v2plus/login", status_code=303))
    html = (ofr.WEB / PAGES[key]).read_text(encoding="utf-8")
    return v2._no_store(Response(html, media_type="text/html; charset=utf-8", headers={"Content-Security-Policy": page_csp(html)}))


async def _redirect(request: Request, db: AsyncSession, to: str) -> Response:
    if not await v2._active_session(request, db):
        return v2._no_store(RedirectResponse(url="/admin-v2plus/login", status_code=303))
    emp = request.query_params.get("empresa")
    if emp and re.match(r"^[0-9a-fA-F-]{8,64}$", emp):
        to += ("&" if "?" in to else "?") + "empresa=" + emp
    return v2._no_store(RedirectResponse(url=to, status_code=303))


@router.get("/admin-v2plus/biblioteca3d", include_in_schema=False)
async def home_noslash(request: Request, db: AsyncSession = Depends(get_db)):
    return await _redirect(request, db, HOME)


@router.get("/admin-v2plus/biblioteca3d/", include_in_schema=False)
async def home_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _page(request, db, "index")


@router.get("/admin-v2plus/biblioteca3d/constructor", include_in_schema=False)
async def constructor_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _page(request, db, "constructor")


@router.get("/admin-v2plus/biblioteca3d/personajes", include_in_schema=False)
async def personajes_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _page(request, db, "personajes")


# rutas viejas de la fase 1 -> pantallas nuevas (la empresa viaja)
@router.get("/admin-v2plus/constructor", include_in_schema=False)
async def old_constructor(request: Request, db: AsyncSession = Depends(get_db)):
    return await _redirect(request, db, HOME + "constructor")


@router.get("/admin-v2plus/constructor/vista", include_in_schema=False)
async def old_vista(request: Request, db: AsyncSession = Depends(get_db)):
    return await _redirect(request, db, HOME + "constructor")


@router.get("/admin-v2plus/biblioteca", include_in_schema=False)
async def old_biblioteca(request: Request, db: AsyncSession = Depends(get_db)):
    return await _redirect(request, db, HOME + "constructor?lib=1")


@router.get("/admin-v2plus/creditos-3d", include_in_schema=False)
async def old_creditos(request: Request, db: AsyncSession = Depends(get_db)):
    return await _redirect(request, db, HOME + "constructor?lib=1")


@router.get("/admin-v2plus/oficina/b3d/{name}", include_in_schema=False)
async def b3d_file(name: str, request: Request, db: AsyncSession = Depends(get_db)):
    await ofr._require(request, db)
    kind = FILES.get(name)
    if not kind:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return v2._no_store(Response((ofr.WEB / "oficina" / "b3d" / name).read_bytes(), media_type=kind))


# ------------------------------------------------------------------ empresas
async def _company(db: AsyncSession, company_id: str) -> dict:
    return await ofr._company(db, company_id)


async def _brand(db: AsyncSession, c: dict) -> dict:
    from app.services import oficina_vivo as ov

    try:
        b = await ov.brand(db, c["id"], c.get("settings"))
    except Exception:
        await db.rollback()
        b = {}
    return b if isinstance(b, dict) else {}


async def _company_out(db: AsyncSession, c: dict, row: Optional[dict] = None) -> dict:
    row = row if row is not None else await od.floor_row(db, c["id"])
    b = await _brand(db, c)
    return {"id": c["id"], "name": c["name"], "kind": c2.TEMPLATE_FOR_FLOOR.get(ofr._template(c, row), "oficina"),
            "brand": c2.brand_colors(b), "neon": str(c["name"] or "")[:24], "logo_url": b.get("logo_url") or ""}


@router.get(API + "/empresas", include_in_schema=False, dependencies=GUARD)
async def empresas(db: AsyncSession = Depends(get_db)):
    out = []
    for c in await od.registered_companies(od.Reader(db)):
        out.append(await _company_out(db, c))
    return _json({"ok": True, "items": out})


def _library(items: list[dict]) -> list[dict]:
    """Modelos 3D de la Biblioteca (Poly Haven CC0 del repo y subidos al bucket) en el formato del catálogo del prototipo."""
    out = []
    for it in console_items([x for x in items if x.get("origen") in ("recurso", "bucket")]):
        m = it.get("medidas") or {}
        out.append({"id": it["id"], "name": it["nombre"], "cat": c2.CAT_FROM_V1.get(it["categoria"], it["categoria"]),
                    "w": m.get("w") or 0.6, "d": m.get("d") or 0.6, "h": m.get("h") or 0.6, "url": it.get("url") or "", "mini": it.get("mini") or "",
                    "license": it.get("licencia") or "", "source": it.get("fuente") or "", "author": it.get("autor") or "",
                    "conn": it.get("conectable") if it.get("conectable") in c2.CONN_PREFIX else None, "state": it.get("estado")})
    return out


async def _glb(db: AsyncSession) -> dict[str, dict]:
    return {m["id"]: m for m in _library(await cb.catalog(db))}


async def _library_state(db: AsyncSession) -> dict:
    items = await cb.catalog(db, ("publicado", "revision"))
    lib = _library(items)
    return {"catalog": [x for x in lib if x["state"] == "publicado"], "review": [x for x in lib if x["state"] == "revision"]}


async def _floor(db: AsyncSession, cid: str) -> tuple[dict, str]:
    row = await od.floor_row(db, cid)
    privacy = row.get("privacidad") if row.get("privacidad") in ("nombre", "cargo") else "nombre"
    return row, privacy


async def _on_shift(db: AsyncSession, cid: str) -> set:
    shifts = await od.open_shifts(od.Reader(db), cid, ofr._now()) or []
    return {str(s.get("employee_id")) for s in shifts if s.get("employee_id")}


async def _state(db: AsyncSession, c: dict) -> dict:
    row, privacy = await _floor(db, c["id"])
    lib = await _library_state(db)
    glb_ids = {m["id"] for m in lib["catalog"]}
    designs = await c2.designs(db, c["id"], glb_ids)
    for d in designs:
        key = d.pop("thumb_key", None)
        d["thumb"] = f"{API}/empresas/{c['id']}/disenos/{d['id']}/miniatura.jpg?v={hashlib.sha256(str(key).encode()).hexdigest()[:10]}" if key else ""
    template = ofr._template(c, row)
    return {"ok": True, "company": await _company_out(db, c, row), "style": await c2.style(db, c["id"]), "designs": designs,
            "team": await c2.team(db, c["id"], template, privacy, await _on_shift(db, c["id"])), "uniforms": await c2.uniforms(db, c["id"]),
            "entities": await c2.entities(db, c["id"], privacy), "areas": list(c2.AREAS), **lib}


@router.get(API + "/empresas/{company_id}", include_in_schema=False, dependencies=GUARD)
async def empresa(company_id: str, db: AsyncSession = Depends(get_db)):
    return _json(await _state(db, await _company(db, company_id)))


async def _body(request: Request) -> Any:
    try:
        return await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Datos no válidos.") from None


def _did(did: str) -> str:
    if not DID_RE.match(did or ""):
        raise HTTPException(status_code=404, detail="Diseño no encontrado.")
    return did


def _drop(cid: str) -> None:
    ofr.reset_db_cache()
    l3.drop_live(cid)
    l3.forget(cid)


@router.put(API + "/empresas/{company_id}/estilo", include_in_schema=False, dependencies=GUARD)
async def estilo(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    body = await _body(request)
    mode = (body or {}).get("style") if isinstance(body, dict) else None
    if mode not in c2.STYLES:
        raise HTTPException(status_code=422, detail="Estilo no válido.")
    await c2.set_style(db, c["id"], mode, ACTOR)
    _drop(c["id"])
    await _audit(request, b3d_estilo=c["id"], estilo=mode)
    return _json({"ok": True, "style": mode})


# ------------------------------------------------------------------ diseños
def _thumb_bytes(raw: Any) -> Optional[bytes]:
    if not isinstance(raw, str) or not raw.startswith("data:image/jpeg;base64,"):
        return None
    try:
        data = base64.b64decode(raw.split(",", 1)[1], validate=True)
    except Exception:
        raise HTTPException(status_code=422, detail="Miniatura no válida.") from None
    if len(data) > c2.THUMB_MAX or not data.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=422, detail="Miniatura no válida.")
    return data


def _put_thumb(cid: str, did: str, data: bytes) -> Optional[str]:
    """Miniatura del diseño al bucket PRIVADO (nunca a Postgres). Si el bucket no responde, el diseño se guarda igual."""
    key = f"{THUMB_PREFIX}{cid}/{did}-{hashlib.sha256(data).hexdigest()[:12]}.jpg"
    try:
        cb.put(key, data, "image/jpeg")
    except Exception:
        return None
    return key


@router.put(API + "/empresas/{company_id}/disenos/{did}", include_in_schema=False, dependencies=GUARD)
async def guardar_diseno(company_id: str, did: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    did = _did(did)
    if int(request.headers.get("content-length") or 0) > c2.MAX_BYTES + c2.THUMB_MAX * 2:
        raise HTTPException(status_code=413, detail="El diseño es demasiado grande.")
    body = await _body(request)
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Datos no válidos.")
    try:
        plan = c2.clean_plan(body.get("plan"), await _glb(db))
        name = c2._text(body.get("name"), 60, "Nombre") or plan["name"]
    except c2.Rejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    if not await c2.design_exists(db, c["id"], did) and await c2.count_designs(db, c["id"]) >= c2.DESIGNS_MAX:
        raise HTTPException(status_code=409, detail=f"Máximo {c2.DESIGNS_MAX} diseños por empresa: borra alguno.")
    thumb = _thumb_bytes(body.get("thumb"))
    key = await asyncio.to_thread(_put_thumb, c["id"], did, thumb) if thumb else None
    saved = await c2.save_design(db, c["id"], did, name, plan, ACTOR, key)
    out = {"ok": True, **saved}
    if key:
        out["thumb"] = f"{API}/empresas/{c['id']}/disenos/{did}/miniatura.jpg?v={hashlib.sha256(key.encode()).hexdigest()[:10]}"
    return _json(out)


@router.delete(API + "/empresas/{company_id}/disenos/{did}", include_in_schema=False, dependencies=GUARD)
async def borrar_diseno(company_id: str, did: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    ok = await c2.delete_design(db, c["id"], _did(did))
    if not ok:
        raise HTTPException(status_code=404, detail="Diseño no encontrado.")
    _drop(c["id"])
    await _audit(request, b3d_borra_diseno=c["id"], diseno=did)
    return _json({"ok": True})


@router.post(API + "/empresas/{company_id}/disenos/{did}/publicar", include_in_schema=False, dependencies=GUARD)
async def publicar(company_id: str, did: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    did = _did(did)
    plan = await c2.draft_plan(db, c["id"], did)
    if plan is None:
        raise HTTPException(status_code=404, detail="Diseño no encontrado.")
    try:
        plan = c2.clean_plan(plan, await _glb(db))
    except c2.Rejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    version = await c2.publish(db, c["id"], did, plan, ACTOR)
    _drop(c["id"])
    await _audit(request, b3d_publica=c["id"], diseno=did, version=version)
    return _json({"ok": True, "version": version})


@router.get(API + "/empresas/{company_id}/disenos/{did}/versiones", include_in_schema=False, dependencies=GUARD)
async def versiones(company_id: str, did: str, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    return _json({"ok": True, "items": await c2.versions(db, c["id"], _did(did))})


@router.get(API + "/empresas/{company_id}/disenos/{did}/versiones/{n}", include_in_schema=False, dependencies=GUARD)
async def version(company_id: str, did: str, n: int, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    plan = await c2.version_plan(db, c["id"], _did(did), n, set(await _glb(db)))
    if plan is None:
        raise HTTPException(status_code=404, detail="Esa versión no existe.")
    return _json({"ok": True, "version": n, "plan": plan})


@router.get(API + "/empresas/{company_id}/disenos/{did}/miniatura.jpg", include_in_schema=False, dependencies=GUARD)
async def miniatura(company_id: str, did: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text

    c = await _company(db, company_id)
    key = (await db.execute(text("""SELECT miniatura FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND diseno_id = :d
        AND estado = 'borrador'"""), {"c": c["id"], "d": _did(did)})).scalar()
    if not key or not str(key).startswith(f"{THUMB_PREFIX}{c['id']}/"):
        raise HTTPException(status_code=404, detail="Sin miniatura.")
    try:
        raw = await asyncio.to_thread(cb.get, key)
    except Exception:
        raise HTTPException(status_code=404, detail="Sin miniatura.") from None
    return Response(raw, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.post(API + "/empresas/{company_id}/importar", include_in_schema=False, dependencies=GUARD)
async def importar(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    if int(request.headers.get("content-length") or 0) > c2.MAX_BYTES * 2:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande.")
    raw = await request.body()
    try:
        plan = c2.import_doc(raw, await _glb(db))
    except c2.Rejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    await _audit(request, b3d_importa=c["id"], objetos=len(plan["objects"]))
    return _json({"ok": True, "plan": plan})


# ------------------------------------------------------------------ equipo y uniformes
@router.put(API + "/empresas/{company_id}/equipo/{pid}", include_in_schema=False, dependencies=GUARD)
async def guardar_persona(company_id: str, pid: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    if not c2.PID_RE.match(pid or ""):
        raise HTTPException(status_code=404, detail="Persona no encontrada.")
    body = await _body(request)
    try:
        look = c2.clean_look(body)
    except c2.Rejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    if pid not in await c2.real_keys(db, c["id"]):
        # "Nuevo personaje" (no ligado al Personal): también es solo de ESTA empresa
        look.update(extra=True, role=c2._text(body.get("role"), 40, "Cargo") or "Mesero/a", shift=c2._text(body.get("shift"), 40, "Turno") or "Turno noche")
    await c2.save_person(db, c["id"], pid, look, ACTOR)
    _drop(c["id"])
    return _json({"ok": True})


@router.put(API + "/empresas/{company_id}/uniformes", include_in_schema=False, dependencies=GUARD)
async def guardar_uniformes(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    body = await _body(request)
    try:
        items = c2.clean_uniforms((body or {}).get("items") if isinstance(body, dict) else None)
    except c2.Rejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    await c2.save_uniforms(db, c["id"], items, ACTOR)
    return _json({"ok": True, "items": items})


@router.post(API + "/empresas/{company_id}/aplicar-marca", include_in_schema=False, dependencies=GUARD)
async def aplicar_marca(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Mismas reglas del prototipo: neón con el nombre, luces LED y pista, sofás/tapetes, sillas, caja, cabina DJ y
    uniformes. Cambia los BORRADORES (lo publicado sigue igual; se puede volver atrás desde "Versiones")."""
    c = await _company(db, company_id)
    co = await _company_out(db, c)
    brand = co["brand"]
    glb = await _glb(db)
    n = 0
    for d in await c2.designs(db, c["id"], set(glb)):
        plan = d["plan"]
        n += c2.apply_brand_to_plan(plan, brand, co["neon"])
        try:
            plan = c2.clean_plan(plan, glb)
        except c2.Rejected:
            continue
        await c2.save_design(db, c["id"], d["id"], d["name"], plan, ACTOR)
    us = await c2.uniforms(db, c["id"])
    c2.apply_brand_to_uniforms(us, brand)
    us = c2.clean_uniforms(us)
    await c2.save_uniforms(db, c["id"], us, ACTOR)
    row, privacy = await _floor(db, c["id"])
    for p in await c2.team(db, c["id"], ofr._template(c, row), privacy, set()):
        u = next((x for x in us if x["id"] == p.get("uniform")), None)
        if not u:
            continue
        look = {"name": p["name"] if not p["real"] else "", "area": p["area"], "toon": {**p["toon"], **u["toon"]}, "human": {**p["human"], **u["human"]},
                "uniform": u["id"], "custom": True}
        if not p["real"]:
            look.update(extra=True, role=p.get("role"), shift=p.get("shift"), name=p["name"])
        await c2.save_person(db, c["id"], p["id"], look, ACTOR)
    _drop(c["id"])
    await _audit(request, b3d_aplica_marca=c["id"], objetos=n, uniformes=len(us))
    return _json({"ok": True, "objects": n, "uniforms": len(us)})


# ------------------------------------------------------------------ biblioteca: subir y revisar (conversión del servidor)
@router.post(API + "/biblioteca/subir", include_in_schema=False, dependencies=GUARD)
async def subir(request: Request, db: AsyncSession = Depends(get_db)):
    if int(request.headers.get("content-length") or 0) > cb.MAX_UPLOAD + 1024 * 1024:
        raise HTTPException(status_code=413, detail="El archivo pasa de 50 MB.")
    form = await request.form()
    up = form.get("archivo")
    if up is None or not hasattr(up, "read"):
        raise HTTPException(status_code=422, detail="Elige el archivo del modelo.")
    cat = str(form.get("categoria") or "")
    try:
        fields = cb.clean_form({"nombre": form.get("nombre"), "categoria": c2.CAT_TO_V1.get(cat, cat), "zonas": "otra", "conectable": "ninguno",
                                "licencia": form.get("licencia"), "fuente": form.get("fuente"), "atribucion": form.get("atribucion"), "alto": form.get("alto")})
    except cb.Rejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    raw = await up.read(cb.MAX_UPLOAD + 1)
    if len(raw) > cb.MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="El archivo pasa de 50 MB.")
    try:
        prep = await asyncio.to_thread(cb.convert, str(getattr(up, "filename", "") or "modelo"), raw, fields["alto"], fields["ancho"])
    except cb.Rejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    try:
        saved = await cb.store(db, fields, prep, hashlib.sha256(raw).hexdigest(), ACTOR)
    except Exception as error:
        if type(error).__name__ == "StorageUnavailable":
            raise HTTPException(status_code=503, detail=str(error)) from None
        raise
    await _audit(request, biblioteca_sube=saved["id"], estado=saved["estado"], licencia=fields["licencia_clave"])
    return _json({"ok": True, **saved, **(await _library_state(db))})


@router.post(API + "/biblioteca/{item_id}/{accion}", include_in_schema=False, dependencies=GUARD)
async def revisar(item_id: str, accion: str, request: Request, db: AsyncSession = Depends(get_db)):
    state = {"aprobar": "publicado", "rechazar": "rechazado"}.get(accion)
    if not state or not re.match(r"^[a-z0-9_-]{2,60}$", item_id):
        raise HTTPException(status_code=404, detail="No encontrado.")
    try:
        ok = await cb.set_state(db, item_id, state, ACTOR)
    except cb.Rejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    if not ok:
        raise HTTPException(status_code=404, detail="Ese objeto no está en revisión.")
    await _audit(request, biblioteca=item_id, accion=accion)
    return _json({"ok": True, "id": item_id, "estado": state, **(await _library_state(db))})


# ------------------------------------------------------------------ archivos del catálogo
def _public_item(x: dict, base: str) -> dict:
    out = {k: x.get(k) for k in ("id", "nombre", "categoria", "origen", "forma", "medidas", "conectable", "licencia", "fuente", "autor",
                                  "atribucion", "estado")}
    if x.get("origen") == "recurso" and x.get("archivo"):
        meta = ofr.manifest().get("files", {}).get(x["archivo"]) or {}
        out["url"] = f"{base}recursos/{x['archivo']}?v={str(meta.get('sha', ''))[:12]}"
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


# ------------------------------------------------------------------ plano PUBLICADO para el motor 3D (oficina y visor del cliente)
async def engine_payload(db: AsyncSession, cid: str, plan: dict, version: Optional[int], base: str, settings: dict) -> dict:
    """Lo mismo que dibuja el editor (room.js + char.js), en el estilo de la empresa. Sin nombres: las personas van por
    su huella y su personaje; las conexiones solo a entidades reales de ESA empresa."""
    row, privacy = await _floor(db, cid)
    ents = await c2.entities(db, cid, privacy)
    ids = {e["id"] for lst in ents.values() for e in lst}
    used = {o["item"] for o in plan.get("objects", [])}
    lib = []
    for it in [_public_item(x, base) for x in await cb.catalog(db) if x["id"] in used and x.get("origen") in ("recurso", "bucket")]:
        m = it.get("medidas") or {}
        lib.append({"id": it["id"], "name": it["nombre"], "cat": c2.CAT_FROM_V1.get(it["categoria"], it["categoria"]), "w": m.get("w") or .6,
                    "d": m.get("d") or .6, "h": m.get("h") or .6, "url": it.get("url") or "", "mini": it.get("mini") or ""})
    looks = await c2.looks_for_engine(db, cid)
    return {"ok": True, "version": version, "plano": c2.for_engine(plan, ids), "estilo": settings.get("estilo_escena") or "humano",
            "catalogo": lib, "looks": looks}


@router.get("/admin-v2/api/oficina/pisos/{company_id}/plano", include_in_schema=False, dependencies=GUARD)
async def plano_motor(company_id: str, db: AsyncSession = Depends(get_db)):
    c = await _company(db, company_id)
    live = await c2.live_plan(db, c["id"], set(await _glb(db)))
    if not live:
        raise HTTPException(status_code=404, detail="Esta empresa no tiene plano publicado en vivo.")
    st = {"estilo_escena": "caricatura" if await c2.style(db, c["id"]) == "toon" else "humano"}
    out = await engine_payload(db, c["id"], live["plano"], live["version"], CONSOLE_BASE, st)
    for it in out["catalogo"]:
        for k in ("url", "mini"):
            if it.get(k, "").startswith(CONSOLE_BASE + "api/"):
                it[k] = it[k].replace(CONSOLE_BASE + "api/", "/admin-v2/api/oficina/")
    out.update(name=c["name"], brand=await _brand(db, c))
    return _json(out)
