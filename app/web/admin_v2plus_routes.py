"""Consola v2+ (/admin-v2plus): la nueva consola principal, en paralelo.

/admin-v2 no se toca y sigue funcionando hasta que esta haga todo lo que hace
la actual. Usa la MISMA sesion de Admin V2 (validada en el servidor con
_active_session). Las imagenes salen de la ruta que ya existe,
/admin-v2-assets/.

Entrada propia (/admin-v2plus/login): pide la huella apenas abre (llave de
acceso WebAuthn: Windows Hello, Touch ID, huella del celular) y deja "Entrar
con clave" como alternativa. Cualquiera de las dos abre la misma sesion.
- Registrar o quitar huellas: solo con sesion (401 sin ella).
- Los dos pasos de entrada con huella son publicos, como el formulario de
  clave: sin ellos no se podria entrar. Comparten el limite de 5 fallos por
  IP en 15 minutos con la clave y solo aceptan llaves ya registradas.
"""
from __future__ import annotations

import html
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import admin_passkeys as pk
from app.web import admin_v2_routes as v2

router = APIRouter()
WEB_DIR = Path(__file__).resolve().parent
_active_session = v2._active_session
_no_store = v2._no_store
HOME = "/admin-v2plus"
LOGIN = "/admin-v2plus/login"


def _file(name: str, media_type: str | None = None) -> FileResponse:
    path = WEB_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo de la Consola v2+ no encontrado")
    return _no_store(FileResponse(path, media_type=media_type))


async def _require_session_json(request: Request, db: AsyncSession) -> None:
    if not await _active_session(request, db):
        raise HTTPException(status_code=401, detail="Sesión de Admin V2 requerida.")


# ------------------------------------------------------------------ paginas
@router.get("/admin-v2plus", include_in_schema=False)
@router.get("/admin-v2plus/", include_in_schema=False)
async def admin_v2plus_page(request: Request, db: AsyncSession = Depends(get_db)):
    if not await _active_session(request, db):
        return _no_store(RedirectResponse(url=LOGIN, status_code=303))
    return _file("admin_v2plus.html", "text/html")


def login_page(error: str = "", *, has_passkeys: bool = False) -> str:
    page = (WEB_DIR / "admin_v2plus_login.html").read_text(encoding="utf-8")
    return (page.replace("__HAS_PASSKEYS__", "true" if has_passkeys else "false")
                .replace("__ERROR__", html.escape(error))
                .replace("__ERROR_HIDDEN__", "" if error else "hidden")
                .replace("__UNSET__", "true" if v2.master_access_mode() == "unset" else "false"))


@router.get("/admin-v2plus/login", include_in_schema=False)
async def admin_v2plus_login_page(request: Request, db: AsyncSession = Depends(get_db)):
    if await _active_session(request, db):
        return RedirectResponse(url=HOME, status_code=303)
    has = bool(await pk.list_passkeys(db))
    return _no_store(HTMLResponse(login_page(has_passkeys=has)))


@router.post("/admin-v2plus/login", include_in_schema=False)
async def admin_v2plus_password_login(request: Request, db: AsyncSession = Depends(get_db)):
    """Entrar con clave (la misma verificacion y el mismo limite de Admin V2)."""
    try:
        email = await v2.verify_password_login(request)
    except v2.LoginRejected as error:
        has = bool(await pk.list_passkeys(db))
        return v2.login_rejected_html(error, page=lambda message: login_page(message, has_passkeys=has))
    return await v2.start_admin_session(request, db, RedirectResponse(url=HOME, status_code=303), email, "password")


@router.get("/admin-v2plus.css", include_in_schema=False)
async def admin_v2plus_css():
    return _file("admin_v2plus.css", "text/css")


@router.get("/admin-v2plus.js", include_in_schema=False)
async def admin_v2plus_js():
    return _file("admin_v2plus.js", "application/javascript")


@router.get("/admin-v2plus-companies.js", include_in_schema=False)
async def admin_v2plus_companies_js():
    return _file("admin_v2plus_companies.js", "application/javascript")


@router.get("/admin-v2plus-palette.js", include_in_schema=False)
async def admin_v2plus_palette_js():
    return _file("admin_v2plus_palette.js", "application/javascript")


@router.get("/admin-v2plus-catalog.js", include_in_schema=False)
async def admin_v2plus_catalog_js():
    return _file("admin_v2plus_catalog.js", "application/javascript")


@router.get("/admin-v2plus-admin.js", include_in_schema=False)
async def admin_v2plus_admin_js():
    return _file("admin_v2plus_admin.js", "application/javascript")


@router.get("/admin-v2plus-ficha.js", include_in_schema=False)
async def admin_v2plus_ficha_js():
    return _file("admin_v2plus_ficha.js", "application/javascript")


@router.get("/admin-v2plus-company.js", include_in_schema=False)
async def admin_v2plus_company_js():
    return _file("admin_v2plus_company.js", "application/javascript")


@router.get("/admin-v2plus-audit.js", include_in_schema=False)
async def admin_v2plus_audit_js():
    return _file("admin_v2plus_audit.js", "application/javascript")


@router.get("/admin-v2plus-login.js", include_in_schema=False)
async def admin_v2plus_login_js():
    return _file("admin_v2plus_login.js", "application/javascript")


@router.get("/admin-v2plus-webauthn.js", include_in_schema=False)
async def admin_v2plus_webauthn_js():
    return _file("webauthn_browser.js", "application/javascript")


# ------------------------------------------------------- entrar con huella
def _webauthn():
    import webauthn
    from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    return webauthn, base64url_to_bytes, bytes_to_base64url, AuthenticatorSelectionCriteria, \
        PublicKeyCredentialDescriptor, ResidentKeyRequirement, UserVerificationRequirement


def _rejected_json(error: v2.LoginRejected) -> JSONResponse:
    response = JSONResponse({"ok": False, "detail": error.message}, status_code=error.status_code)
    if error.retry_after:
        response.headers["Retry-After"] = str(error.retry_after)
    return _no_store(response)


@router.post("/admin-v2plus/api/passkey/login/options", include_in_schema=False)
async def passkey_login_options(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        v2.check_login_allowed(request)
    except v2.LoginRejected as error:
        return _rejected_json(error)
    rows = await pk.list_passkeys(db)
    if not rows:
        return _no_store(JSONResponse({"ok": False, "detail": "No hay huellas registradas. Entra con tu clave."}, status_code=404))
    webauthn, b64_to_bytes, _b2, _sel, Descriptor, _rk, UV = _webauthn()
    options = webauthn.generate_authentication_options(
        rp_id=pk.rp_id(request),
        allow_credentials=[Descriptor(id=b64_to_bytes(r["credential_id"])) for r in rows],
        user_verification=UV.REQUIRED,
    )
    response = JSONResponse({"ok": True, "options": json.loads(webauthn.options_to_json(options))})
    pk.set_challenge(response, request, options.challenge, "login")
    return _no_store(response)


@router.post("/admin-v2plus/api/passkey/login/verify", include_in_schema=False)
async def passkey_login_verify(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        ip = v2.check_login_allowed(request)
    except v2.LoginRejected as error:
        return _rejected_json(error)
    challenge = pk.read_challenge(request, "login")
    body = await request.json()
    credential = body.get("credential") if isinstance(body, dict) else None
    row = await pk.find_passkey(db, str((credential or {}).get("rawId") or (credential or {}).get("id") or "")) \
        if isinstance(credential, dict) else None
    if not challenge or not row:
        v2._register_failure(ip)
        return _rejected_json(v2.LoginRejected(401, "Huella no reconocida. Intenta de nuevo o entra con tu clave."))
    webauthn, *_rest = _webauthn()
    try:
        verified = webauthn.verify_authentication_response(
            credential=credential, expected_challenge=challenge, expected_rp_id=pk.rp_id(request),
            expected_origin=pk.expected_origin(request), credential_public_key=bytes(row["public_key"]),
            credential_current_sign_count=int(row["sign_count"] or 0), require_user_verification=True,
        )
    except Exception:
        v2._register_failure(ip)
        return _rejected_json(v2.LoginRejected(401, "Huella no reconocida. Intenta de nuevo o entra con tu clave."))
    v2._clear_failures(ip)
    await pk.touch_passkey(db, row["credential_id"], verified.new_sign_count)
    response = JSONResponse({"ok": True, "redirect": HOME})
    pk.clear_challenge(response)
    return _no_store(await v2.start_admin_session(request, db, response, v2.ADMIN_V2_EMAIL, "passkey"))


# --------------------------------------------- registrar huellas (con sesion)
@router.get("/admin-v2plus/api/passkeys", include_in_schema=False)
async def passkeys_list(request: Request, db: AsyncSession = Depends(get_db)):
    await _require_session_json(request, db)
    ready = await pk.table_ready(db)
    return _no_store(JSONResponse({"ok": True, "ready": ready, "passkeys": [pk.public_row(r) for r in await pk.list_passkeys(db)]}))


@router.post("/admin-v2plus/api/passkeys/register/options", include_in_schema=False)
async def passkeys_register_options(request: Request, db: AsyncSession = Depends(get_db)):
    await _require_session_json(request, db)
    if not await pk.table_ready(db):
        raise HTTPException(status_code=503, detail="Falta la migración 022p_admin_passkeys.")
    webauthn, b64_to_bytes, _b2, Selection, Descriptor, ResidentKey, UV = _webauthn()
    options = webauthn.generate_registration_options(
        rp_id=pk.rp_id(request), rp_name=pk.RP_NAME, user_id=pk.user_handle(v2.ADMIN_V2_EMAIL),
        user_name=v2.ADMIN_V2_EMAIL, user_display_name="Acceso maestro CLONEXA",
        exclude_credentials=[Descriptor(id=b64_to_bytes(r["credential_id"])) for r in await pk.list_passkeys(db)],
        authenticator_selection=Selection(resident_key=ResidentKey.PREFERRED, user_verification=UV.REQUIRED),
    )
    response = JSONResponse({"ok": True, "options": json.loads(webauthn.options_to_json(options))})
    pk.set_challenge(response, request, options.challenge, "register")
    return _no_store(response)


@router.post("/admin-v2plus/api/passkeys/register/verify", include_in_schema=False)
async def passkeys_register_verify(request: Request, db: AsyncSession = Depends(get_db)):
    await _require_session_json(request, db)
    challenge = pk.read_challenge(request, "register")
    body = await request.json()
    credential = body.get("credential") if isinstance(body, dict) else None
    label = str((body or {}).get("label") or "Equipo").strip()[:120] or "Equipo"
    if not challenge or not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="El registro venció. Vuelve a intentarlo.")
    webauthn, _b1, b2, *_rest = _webauthn()
    try:
        verified = webauthn.verify_registration_response(
            credential=credential, expected_challenge=challenge, expected_rp_id=pk.rp_id(request),
            expected_origin=pk.expected_origin(request), require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="No se pudo verificar la huella de este equipo.") from exc
    transports = (credential.get("response") or {}).get("transports") or []
    await pk.add_passkey(db, b2(verified.credential_id), verified.credential_public_key, verified.sign_count, label,
                         [str(t) for t in transports][:6])
    response = JSONResponse({"ok": True, "passkeys": [pk.public_row(r) for r in await pk.list_passkeys(db)]})
    pk.clear_challenge(response)
    return _no_store(response)


@router.delete("/admin-v2plus/api/passkeys/{passkey_id}", include_in_schema=False)
async def passkeys_delete(passkey_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _require_session_json(request, db)
    try:
        uuid.UUID(passkey_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Huella no encontrada.") from exc
    if not await pk.delete_passkey(db, passkey_id):
        raise HTTPException(status_code=404, detail="Huella no encontrada.")
    return _no_store(JSONResponse({"ok": True, "passkeys": [pk.public_row(r) for r in await pk.list_passkeys(db)]}))
