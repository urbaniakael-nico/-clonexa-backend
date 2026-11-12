"""NEGOCIO EN VIVO 3D (modulo live3d): tarjeta de la consola, acceso del cliente y visor de SU piso.

Consola v2+ (GUARD = sesion de Admin V2, 401 antes de leer el cuerpo):
- GET  /admin-v2/api/companies/{id}/live3d             tarjeta: interruptor, plantilla, privacidad, quien lo ve, TV,
                                                       liviano y consumo (pantallas abiertas ahora y bytes del mes).
- PUT  /admin-v2/api/companies/{id}/live3d             guardar (con auditoria). Plantilla/privacidad = la MISMA fila
                                                       oficina_pisos de la Oficina 3D (una sola fuente).
- POST /admin-v2/api/companies/{id}/live3d/abrir       enlace "Abrir como el cliente" (exactamente el visor del cliente).
- GET  /admin-v2/api/companies/{id}/live3d/vista.jpg   imagen del piso (bucket privado).
Panel del cliente (sesion normal: Bearer del portal o la sesion de Admin V2 de "Abrir /client"):
- GET /api/v1/live3d/companies/{id}/acceso     403 si el modulo esta apagado o el rol no esta en "Quien lo ve";
                                               si no, un enlace de un solo uso por 5 min hacia el visor.
- GET /api/v1/live3d/companies/{id}/vista.jpg  la imagen del piso para la tarjeta del panel.
Visor (todo con la cookie HttpOnly firmada de ESA empresa + el enlace firmado de la empresa; 401/403 si no):
- GET /panel/negocio-en-vivo?company_id=       entrada con la cookie vigente (si no: 401; modulo apagado: 403).
- GET /panel/negocio-en-vivo/v/{ticket}        cambia el ticket por la cookie y lleva al visor.
- GET /panel/negocio-en-vivo/r/{id}/{firma}/   el visor (solo su piso, solo lectura, modo TV).
- .../r/{id}/{firma}/{archivo.js|vendor/three/...|recursos/...|bar/...}   motor, three, CC0 y Mixamo (bucket privado).
- .../r/{id}/{firma}/api/{piso|personajes|pisos/{id}/vivo|marca/{id}/logo|vista}
"""
from __future__ import annotations

import copy
import json
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import brand_media
from app.services import live3d as l3
from app.services import oficina as of
from app.services import oficina_bar as obar
from app.services import oficina_data as od
from app.web import admin_v2_routes as v2
from app.web import oficina_routes as ofr
from app.web.admin_v2plus_companies import GUARD, _audit, _json

router = APIRouter()
BASE = "/panel/negocio-en-vivo"
PAGE = ofr.WEB / "oficina" / "vivo3d.html"
ACTOR = "admin_v2"
# Archivos del motor que el visor del cliente puede pedir (nada del edificio, del piso de Clonexa ni de la recepcion).
VIEWER_ASSETS = {k: v for k, v in ofr.ASSETS.items() if k in ("app.css", "bar.js", "bar_reglas.js", "mixamo.js", "pisos_reglas.js", "gestos.js",
                                                             "taller.js", "restaurante.js", "campo.js", "arquitecto.js")}
VIEWER_ASSETS["vivo3d.js"] = ("oficina/vivo3d.js", "application/javascript")
VIEWER_ASSETS["vivo3d.css"] = ("oficina/vivo3d.css", "text/css")


def _secret() -> bytes:
    return v2._session_secret()


def _cid(company_id: Any) -> str:
    try:
        return str(uuid.UUID(str(company_id)))
    except ValueError:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.") from None


def root_of(cid: str) -> str:
    return f"{BASE}/r/{cid}/{l3.link_sig(_secret(), cid)}/"


def _deny(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail, headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ configuracion de una empresa
async def _company(db: AsyncSession, cid: str) -> dict:
    found = next((c for c in await od.registered_companies(od.Reader(db)) if c["id"] == cid), None)
    if not found:
        raise HTTPException(status_code=404, detail="Empresa no encontrada (solo empresas registradas).")
    return found


async def card(db: AsyncSession, c: dict) -> dict:
    row = await od.floor_row(db, c["id"])
    template = ofr._template(c, row)
    st = l3.settings_of(row)
    style = od.floor_style(row, template)
    return {
        "company_id": c["id"], "name": c["name"], "enabled": await l3.module_enabled(db, c["id"]),
        "template": template, "template_label": of.TEMPLATE_LABEL[template], "noun": l3.NOUN.get(template, "negocio"),
        "has_engine": template in l3.WITH_ENGINE and style in ("bar", "aprobado"), "style": style,
        "privacy": row.get("privacidad") if row.get("privacidad") in of.PRIVACY else "nombre",
        "audience": st["audience"], "roles": st["roles"], "tv": st["tv"], "lite": st["lite"],
        "usage": await l3.usage(db, c["id"]),
        "options": {"templates": [{"key": k, "label": of.TEMPLATE_LABEL[k] + ("" if k in l3.WITH_ENGINE else " (sin piso 3D aún)")} for k in of.TEMPLATES],
                    "privacy": [{"key": k, "label": l3.PRIVACY_LABEL[k]} for k in of.PRIVACY],
                    "audience": [{"key": k, "label": l3.AUDIENCE_LABEL[k]} for k in l3.AUDIENCES],
                    "lite": [{"key": k, "label": l3.LITE_LABEL[k]} for k in l3.LITE_MODES]},
    }


@router.get("/admin-v2/api/companies/{company_id}/live3d", include_in_schema=False, dependencies=GUARD)
async def consola_tarjeta(company_id: str, db: AsyncSession = Depends(get_db)):
    c = await _company(db, _cid(company_id))
    return _json({"ok": True, **(await card(db, c))})


@router.put("/admin-v2/api/companies/{company_id}/live3d", include_in_schema=False, dependencies=GUARD)
async def consola_guardar(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await _company(db, _cid(company_id))
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Datos no válidos.") from None
    if not isinstance(body, dict) or not body:
        raise HTTPException(status_code=422, detail="Nada que guardar.")
    floor: dict[str, Any] = {}
    sets: dict[str, Any] = {}
    row = await od.floor_row(db, c["id"])
    if "plantilla" in body:
        if body["plantilla"] not in of.TEMPLATES:
            raise HTTPException(status_code=422, detail="Plantilla no válida.")
        floor["plantilla"] = body["plantilla"]
        floor["estilo"] = l3.STYLE_FOR.get(body["plantilla"], "clasico")
    if "privacidad" in body:
        if body["privacidad"] not in of.PRIVACY:
            raise HTTPException(status_code=422, detail="Privacidad no válida.")
        floor["privacidad"] = body["privacidad"]
    if "audience" in body:
        if body["audience"] not in l3.AUDIENCES:
            raise HTTPException(status_code=422, detail="Opción de quién lo ve no válida.")
        sets["audience"] = body["audience"]
    if "roles" in body:
        try:
            sets["roles"] = l3.clean_roles(body["roles"])
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
    if "tv" in body:
        if not isinstance(body["tv"], bool):
            raise HTTPException(status_code=422, detail="Modo TV no válido.")
        sets["tv"] = body["tv"]
    if "lite" in body:
        if body["lite"] not in l3.LITE_MODES:
            raise HTTPException(status_code=422, detail="Modo liviano no válido.")
        sets["lite"] = body["lite"]
    enabled = body.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        raise HTTPException(status_code=422, detail="Interruptor no válido.")
    if enabled and "estilo" not in floor:
        # al encender: el piso abre su motor aprobado (misma regla que la Oficina 3D)
        template = ofr._template(c, row)
        if template in l3.STYLE_FOR and od.floor_style(row, template) not in ("bar", "aprobado"):
            floor["estilo"] = l3.STYLE_FOR[template]
    if not floor and not sets and enabled is None:
        raise HTTPException(status_code=422, detail="Nada que guardar.")
    if floor:
        await od.save_floor(db, c["id"], actor=ACTOR, **floor)
    if sets:
        await l3.save_settings(db, c["id"], ACTOR, **sets)
    if enabled is not None:
        await l3.set_module(db, c["id"], enabled)
    ofr.reset_db_cache()
    l3.drop_live(c["id"])
    l3.forget(c["id"])
    await _audit(request, live3d=c["id"], **({"encendido": "si" if enabled else "no"} if enabled is not None else {}),
                 campos=",".join(sorted([*floor, *sets])) or "interruptor")
    return _json({"ok": True, **(await card(db, c))})


@router.post("/admin-v2/api/companies/{company_id}/live3d/abrir", include_in_schema=False, dependencies=GUARD)
async def consola_abrir(company_id: str, db: AsyncSession = Depends(get_db)):
    c = await _company(db, _cid(company_id))
    ticket = l3.sign(_secret(), "ticket", {"c": c["id"], "k": "a", "u": "", "e": int(time.time()) + l3.TICKET_TTL})
    return _json({"ok": True, "url": f"{BASE}/v/{ticket}"})


async def _preview_bytes(cid: str) -> Optional[bytes]:
    import asyncio

    try:
        raw = await asyncio.to_thread(brand_media.backend().get, l3.preview_key(cid))
    except Exception:
        return None
    return raw if l3.preview_ok(raw) else None


def _jpeg(raw: bytes) -> Response:
    return Response(raw, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff",
                                                          "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.get("/admin-v2/api/companies/{company_id}/live3d/vista.jpg", include_in_schema=False, dependencies=GUARD)
async def consola_vista(company_id: str, db: AsyncSession = Depends(get_db)):
    c = await _company(db, _cid(company_id))
    raw = await _preview_bytes(c["id"])
    if not raw:
        raise HTTPException(status_code=404, detail="Aún no hay imagen del piso (se toma sola al abrirlo).")
    return _jpeg(raw)


@router.get("/admin-v2plus-live3d.js", include_in_schema=False)
async def consola_js(request: Request, db: AsyncSession = Depends(get_db)):
    """Script de la tarjeta (solo con sesion de Admin V2, como todo lo nuevo)."""
    if not await v2._active_session(request, db):
        raise _deny(401, "Sesión de Admin V2 requerida.")
    return v2._no_store(FileResponse(ofr.WEB / "oficina" / "admin_v2plus_live3d.js", media_type="application/javascript"))


# ------------------------------------------------------------------ acceso del cliente
async def allowed_now(db: AsyncSession, cid: str, role: str) -> bool:
    if not await l3.module_enabled(db, cid):
        return False
    st = l3.settings_of(await od.floor_row(db, cid))
    return l3.role_allowed(role, st["audience"], st["roles"])


async def client_identity(request: Request, db: AsyncSession, cid: str, authorization: Optional[str]) -> dict:
    """Quien pide: usuario del portal (Bearer, de esa empresa) o Admin V2 ("Abrir /client"). 401 sin sesion."""
    if authorization:
        from app.api.deps import extract_bearer_token
        from app.services.auth_service import get_current_company_user

        user = await get_current_company_user(db, extract_bearer_token(authorization))
        if str(getattr(user, "company_id", "")) != cid:
            raise _deny(403, "tenant_not_allowed")
        return {"k": "c", "u": str(user.id), "role": l3.norm_role(getattr(user, "role", ""))}
    if await v2._active_session(request, db):
        return {"k": "a", "u": "", "role": "company_admin"}
    raise _deny(401, "Sesión requerida.")


async def _client_gate(request: Request, db: AsyncSession, company_id: str, authorization: Optional[str]) -> tuple[str, dict]:
    cid = _cid(company_id)
    who = await client_identity(request, db, cid, authorization)
    if not await allowed_now(db, cid, who["role"]):
        raise _deny(403, "Negocio en vivo 3D no está disponible para este usuario.")
    return cid, who


@router.get("/api/v1/live3d/companies/{company_id}/panel", include_in_schema=False)
async def panel(company_id: str, request: Request, authorization: Optional[str] = Header(default=None), db: AsyncSession = Depends(get_db)):
    """Lo que el panel del dueño nuevo (078A) necesita: el interruptor de emergencia del diseño de antes
    (settings_json.owner_panel_classic) y si este usuario ve la tarjeta "Ver mi negocio en vivo" (sin enlace)."""
    cid = _cid(company_id)
    who = await client_identity(request, db, cid, authorization)
    settings = (await db.execute(text("SELECT settings_json FROM companies WHERE id = CAST(:c AS uuid)"), {"c": cid})).scalar()
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except ValueError:
            settings = {}
    classic = isinstance(settings, dict) and settings.get("owner_panel_classic") is True
    live = None
    if await allowed_now(db, cid, who["role"]):
        c = next((x for x in await od.registered_companies(od.Reader(db)) if x["id"] == cid), None)
        if c:
            row = await od.floor_row(db, cid)
            template = ofr._template(c, row)
            if template in l3.WITH_ENGINE and od.floor_style(row, template) in ("bar", "aprobado"):
                live = {"noun": l3.NOUN.get(template, "negocio"), "template": template, "has_preview": bool(await _preview_bytes(cid))}
    return _json({"ok": True, "classic": classic, "live3d": live})


@router.get("/api/v1/live3d/companies/{company_id}/acceso", include_in_schema=False)
async def acceso(company_id: str, request: Request, authorization: Optional[str] = Header(default=None), db: AsyncSession = Depends(get_db)):
    cid, who = await _client_gate(request, db, company_id, authorization)
    c = await _company(db, cid)
    row = await od.floor_row(db, cid)
    template = ofr._template(c, row)
    ticket = l3.sign(_secret(), "ticket", {"c": cid, "k": who["k"], "u": who["u"], "e": int(time.time()) + l3.TICKET_TTL})
    return _json({"ok": True, "url": f"{BASE}/v/{ticket}", "template": template, "noun": l3.NOUN.get(template, "negocio"),
                  "tv": l3.settings_of(row)["tv"], "has_preview": bool(await _preview_bytes(cid))})


@router.get("/api/v1/live3d/companies/{company_id}/vista.jpg", include_in_schema=False)
async def acceso_vista(company_id: str, request: Request, authorization: Optional[str] = Header(default=None), db: AsyncSession = Depends(get_db)):
    cid, _who = await _client_gate(request, db, company_id, authorization)
    raw = await _preview_bytes(cid)
    if not raw:
        raise HTTPException(status_code=404, detail="Aún no hay imagen del piso.")
    return _jpeg(raw)


# ------------------------------------------------------------------ visor: ticket -> cookie -> rutas firmadas
def _set_cookie(response: Response, request: Request, data: dict) -> None:
    cookie = l3.sign(_secret(), "cookie", {"c": data["c"], "k": data["k"], "u": data.get("u") or "", "e": int(time.time()) + l3.COOKIE_TTL})
    response.set_cookie(l3.cookie_name(data["c"]), cookie, max_age=l3.COOKIE_TTL, path=BASE, httponly=True, samesite="strict",
                        secure=v2._is_secure_request(request))


async def _still_allowed(request: Request, db: AsyncSession, data: dict) -> bool:
    if data["k"] == "a":
        return await v2._active_session(request, db)
    row = (await db.execute(text("SELECT role, status FROM company_users WHERE id = CAST(:u AS uuid) AND company_id = CAST(:c AS uuid)"),
                            {"u": data.get("u") or str(uuid.UUID(int=0)), "c": data["c"]})).mappings().first()
    if not row or str(row["status"] or "").lower() != "active":
        return False
    return await allowed_now(db, data["c"], row["role"])


async def viewer_session(request: Request, db: AsyncSession, company_id: str, sig: Optional[str]) -> dict:
    cid = _cid(company_id)
    if sig is not None and sig != l3.link_sig(_secret(), cid):
        raise _deny(404, "No encontrado.")
    data = l3.verify(_secret(), "cookie", request.cookies.get(l3.cookie_name(cid), ""))
    if not data or data["c"] != cid:
        raise _deny(401, "Sesión del visor requerida: ábrelo desde tu panel.")
    if data["k"] == "a":
        ok = await _still_allowed(request, db, data)
    else:
        ok = await l3.recheck(f"{cid}|c|{data.get('u')}", lambda: _still_allowed(request, db, data))
    if not ok:
        raise _deny(403, "Negocio en vivo 3D no está disponible para este usuario.")
    return data


@router.get(BASE, include_in_schema=False)
async def entrada(request: Request, company_id: str = Query(""), db: AsyncSession = Depends(get_db)):
    await viewer_session(request, db, company_id, None)
    return v2._no_store(RedirectResponse(url=root_of(_cid(company_id)), status_code=303))


@router.get(BASE + "/v/{ticket}", include_in_schema=False)
async def canjear(ticket: str, request: Request, db: AsyncSession = Depends(get_db)):
    data = l3.verify(_secret(), "ticket", ticket)
    if not data:
        raise _deny(401, "Enlace vencido: vuelve a abrirlo desde tu panel.")
    if not await _still_allowed(request, db, data):
        raise _deny(403, "Negocio en vivo 3D no está disponible para este usuario.")
    response = v2._no_store(RedirectResponse(url=root_of(data["c"]), status_code=303))
    _set_cookie(response, request, data)
    return response


def page_html(cid: str) -> str:
    root = root_of(cid)
    return PAGE.read_text(encoding="utf-8").replace("__ROOT__", root)


@router.get(BASE + "/r/{company_id}/{sig}/", include_in_schema=False)
async def visor(company_id: str, sig: str, request: Request, db: AsyncSession = Depends(get_db)):
    await viewer_session(request, db, company_id, sig)
    html = page_html(_cid(company_id))
    return v2._no_store(Response(html, media_type="text/html; charset=utf-8", headers={"Content-Security-Policy": ofr.page_csp(html)}))


def _not_modified(request: Request, sha: str) -> bool:
    return request.headers.get("if-none-match", "").strip() == f'"{sha}"'


@router.get(BASE + "/r/{company_id}/{sig}/vendor/three/{path:path}", include_in_schema=False)
async def visor_three(company_id: str, sig: str, path: str, request: Request, db: AsyncSession = Depends(get_db)):
    data = await viewer_session(request, db, company_id, sig)
    if path not in ofr.THREE:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    f = ofr.WEB / ofr.THREE_DIR / path
    l3.count_bytes(data["c"], f.stat().st_size)
    return FileResponse(f, media_type="application/javascript", headers={"Cache-Control": "private, max-age=86400"})


@router.get(BASE + "/r/{company_id}/{sig}/recursos/{path:path}", include_in_schema=False)
async def visor_recurso(company_id: str, sig: str, path: str, request: Request, db: AsyncSession = Depends(get_db)):
    data = await viewer_session(request, db, company_id, sig)
    m = ofr.manifest()
    if path == "manifest.json":
        return v2._no_store(Response(json.dumps({"files": m.get("files", {}), "templates": m.get("templates", {})}), media_type="application/json"))
    meta = m.get("files", {}).get(path)
    if not meta:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    headers = {"Cache-Control": ofr.LONG_CACHE, "ETag": f'"{meta["sha"]}"', "X-Content-Type-Options": "nosniff"}
    if _not_modified(request, meta["sha"]):
        return Response(status_code=304, headers=headers)
    l3.count_bytes(data["c"], int(meta["bytes"]))
    return FileResponse(ofr.RES_DIR / path, media_type=ofr.RES_TYPES.get(path.rsplit(".", 1)[-1], "application/octet-stream"), headers=headers)


@router.get(BASE + "/r/{company_id}/{sig}/bar/{path:path}", include_in_schema=False)
async def visor_mixamo(company_id: str, sig: str, path: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Personajes y animaciones de Mixamo: bucket PRIVADO, solo con la sesion del visor (nunca publicos)."""
    data = await viewer_session(request, db, company_id, sig)
    try:
        if path == "manifest.json":
            mm = await obar.manifest()
            return v2._no_store(Response(json.dumps({"files": mm["files"], "version": mm["version"]}), media_type="application/json"))
        meta = (await obar.manifest())["files"].get(path)
        headers = {"Cache-Control": ofr.LONG_CACHE, "X-Content-Type-Options": "nosniff"}
        if meta and _not_modified(request, meta["sha"]):
            return Response(status_code=304, headers={**headers, "ETag": f'"{meta["sha"]}"'})
        found = await obar.read(path)
    except obar.Unavailable as error:
        raise HTTPException(status_code=503, detail=str(error), headers={"Cache-Control": "no-store"}) from None
    if not found:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    raw, sha = found
    l3.count_bytes(data["c"], len(raw))
    return Response(raw, media_type="model/gltf-binary", headers={**headers, "ETag": f'"{sha}"'})


# ------------------------------------------------------------------ visor: datos (solo SU empresa, solo lectura)
def _for_client(value: Any, cid: str) -> Any:
    """El logo de la marca sale por la ruta del visor (no por la de la consola)."""
    out = copy.deepcopy(value)
    brand = out.get("brand") if isinstance(out, dict) else None
    if isinstance(brand, dict) and brand.get("logo_url"):
        brand["logo_url"] = brand["logo_url"].replace(f"/admin-v2/api/oficina/marca/{cid}/logo", f"{root_of(cid)}api/marca/{cid}/logo")
    return out


def _sized(data: dict, cid: str) -> Response:
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    l3.count_bytes(cid, len(body))
    return v2._no_store(Response(body, media_type="application/json"))


@router.get(BASE + "/r/{company_id}/{sig}/api/piso", include_in_schema=False)
async def visor_piso(company_id: str, sig: str, request: Request, db: AsyncSession = Depends(get_db)):
    data = await viewer_session(request, db, company_id, sig)
    cid = data["c"]
    floor = await od.floor_for(od.Reader(db), cid, ofr._now())
    if not floor:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    st = l3.settings_of(await od.floor_row(db, cid))
    keep = ("company_id", "name", "template", "template_label", "privacy", "style", "brand", "staff")
    out = {k: floor.get(k) for k in keep}
    return _sized({"ok": True, "floor": _for_client(out, cid), "tv": st["tv"], "lite": l3.lite_for(st["lite"]), "noun": l3.NOUN.get(floor["template"], "negocio"),
                   "admin": data["k"] == "a", "back": f"/client?company_id={cid}"}, cid)


@router.get(BASE + "/r/{company_id}/{sig}/api/personajes", include_in_schema=False)
async def visor_personajes(company_id: str, sig: str, request: Request, db: AsyncSession = Depends(get_db)):
    data = await viewer_session(request, db, company_id, sig)
    cid = data["c"]
    items = [x for x in await od.characters(od.Reader(db))
             if (x["company_id"] == cid) or (x["company_id"] is None and str(x["clave"]).startswith("plantilla:"))]
    return _sized({"ok": True, "items": items}, cid)


@router.get(BASE + "/r/{company_id}/{sig}/api/pisos/{floor_id}/vivo", include_in_schema=False)
async def visor_vivo(company_id: str, sig: str, floor_id: str, request: Request, rev: str = Query(""), s: str = Query(""),
                     db: AsyncSession = Depends(get_db)):
    data = await viewer_session(request, db, company_id, sig)
    cid = data["c"]
    if _cid(floor_id) != cid:
        raise _deny(403, "tenant_not_allowed")
    c, row = await ofr._live_company(db, cid)
    l3.heartbeat(cid, s)
    snap = await ofr.company_snapshot(db, c, row)
    await l3.flush(db, cid)
    if rev and rev == snap["rev"]:
        return _sized({"ok": True, "same": True, "rev": snap["rev"]}, cid)
    return _sized(_for_client(snap, cid), cid)


@router.get(BASE + "/r/{company_id}/{sig}/api/marca/{floor_id}/logo", include_in_schema=False)
async def visor_logo(company_id: str, sig: str, floor_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    data = await viewer_session(request, db, company_id, sig)
    cid = data["c"]
    if _cid(floor_id) != cid:
        raise _deny(403, "tenant_not_allowed")
    c = await _company(db, cid)
    from app.services import oficina_vivo as ov

    found = await ov.logo(db, cid, c.get("settings"))
    if not found:
        raise HTTPException(status_code=404, detail="Esta empresa no tiene logo en el Estudio de marca.")
    raw, media_type = found
    l3.count_bytes(cid, len(raw))
    return Response(raw, media_type=media_type, headers={"Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff",
                                                        "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.post(BASE + "/r/{company_id}/{sig}/api/vista", include_in_schema=False)
async def visor_guardar_vista(company_id: str, sig: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Imagen chica (JPEG <= 160 KB) del piso para la tarjeta de la consola y del panel. Va al bucket privado (nunca a
    Postgres) y se reemplaza; a lo sumo una cada 10 min por empresa."""
    data = await viewer_session(request, db, company_id, sig)
    cid = data["c"]
    if not l3.preview_due(cid):
        return _json({"ok": True, "skipped": True})
    raw = await request.body()
    if not l3.preview_ok(raw):
        raise HTTPException(status_code=422, detail="Imagen no válida.")
    import asyncio

    try:
        await asyncio.to_thread(brand_media.put_private, l3.preview_key(cid), raw, "image/jpeg")
    except Exception:
        return _json({"ok": False, "skipped": True})
    l3.preview_saved(cid)
    return _json({"ok": True})


@router.get(BASE + "/r/{company_id}/{sig}/{name}", include_in_schema=False)
async def visor_archivo(company_id: str, sig: str, name: str, request: Request, db: AsyncSession = Depends(get_db)):
    data = await viewer_session(request, db, company_id, sig)
    item = VIEWER_ASSETS.get(name)
    if not item:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    f = ofr.WEB / item[0]
    l3.count_bytes(data["c"], f.stat().st_size)
    return v2._no_store(FileResponse(f, media_type=item[1]))

