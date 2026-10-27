"""Menu video: foto del plato (todas las empresas con Carta), video del plato
y cupo mensual (interruptor carta_video), y el regreso de la lectura de la
carta desde n8n.

- /menu-video/companies/{company_id}/...: sesion de la empresa con rol
  administrador/dueño/gerente (o Admin V2) y el modulo carta activo, igual que
  la Carta (require_carta_admin).
- POST /menu-video/import-callback: token de servicio X-Carta-Token comparado
  en tiempo constante contra CARTA_IMPORT_TOKEN (sin variable 503, mal 401;
  el cuerpo se valida despues: JSON invalido 422).
"""
from __future__ import annotations

import hmac
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.carta import require_carta_admin
from app.services import brand_media
from app.services import menu_media as mm
from app.services import menu_video as mv

router = APIRouter()
MAX_PHOTO_BYTES = mm.MAX_UPLOAD_BYTES


# ------------------------------------------------------------- utilidades ---
def _media_error(error: Exception) -> HTTPException:
    if isinstance(error, brand_media.StorageUnavailable):
        return HTTPException(status_code=503, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


def _quota_error(error: mv.QuotaExceeded) -> HTTPException:
    word = "platos nuevos con foto" if error.kind == "nuevo" else "cambios de foto o video"
    limit = error.state["new" if error.kind == "nuevo" else "changes"]["limit"]
    return HTTPException(status_code=409, detail={
        "code": "sin_cupo", "kind": error.kind, "quota": error.state,
        "message": f"Ya usaste los {limit} {word} de este mes. Puedes solicitar más cupo."})


async def _dish(db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID) -> dict:
    row = (await db.execute(text("""
        SELECT id::text AS id, name FROM carta_items WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"i": str(item_id), "c": str(company_id)})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Plato no encontrado.")
    return dict(row)


async def _read_upload(upload: Optional[UploadFile]) -> Optional[tuple[bytes, str]]:
    if upload is None or not getattr(upload, "filename", None):
        return None
    raw = await upload.read(MAX_PHOTO_BYTES + 1)
    if len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="La foto pesa más de 15 MB.")
    if not raw:
        return None
    return raw, upload.filename or ""


async def portal_state(db: AsyncSession, company_id: uuid.UUID) -> dict:
    cid = str(company_id)
    video = await mv.video_on(db, cid)
    media = await mv.media_map(db, cid, video=video)
    out: dict[str, Any] = {"company_id": cid, "carta_video": video, "media": media}
    if video:
        out["quota"] = await mv.quota_state(db, cid)
        out["jobs"] = await mv.jobs_for(db, cid)
        out["styles"] = mm.STYLES
    return out


# --------------------------------------------------------------- portal ---
@router.get("/companies/{company_id}/portal")
async def portal(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _a: str = Depends(require_carta_admin)) -> dict:
    return await portal_state(db, company_id)


async def audit(request: Request, company_id: str, actor: str, **detail: Any) -> None:
    """057D: queda en la auditoria de la empresa quien cambio o quito que foto y
    cuando (la misma tabla que ve la Ficha en v2+). Nunca rompe la accion."""
    try:
        from app.services import admin_audit

        await admin_audit.write_entry({
            "actor": f"{actor} (portal)"[:200], "ip": admin_audit.client_ip(dict(request.headers), request.client),
            "method": request.method, "path": request.url.path[:500], "company_id": company_id, "status_code": 200,
            "surface": "portal", "detail": admin_audit.clean_detail(detail)})
    except Exception as exc:
        import logging

        logging.getLogger("clonexa.menu_video").warning("auditoria de foto no registrada: %s", type(exc).__name__)


ROLE_WORDS = {"top": "desde arriba", "front": "de frente", "side": "de perfil"}


@router.post("/companies/{company_id}/items/{item_id}/photo")
async def upload_photo(company_id: uuid.UUID, item_id: uuid.UUID, request: Request, front: Optional[UploadFile] = File(default=None),
                       side: Optional[UploadFile] = File(default=None), top: Optional[UploadFile] = File(default=None),
                       style: str = Form(default="auto"),
                       db: AsyncSession = Depends(get_db), actor: str = Depends(require_carta_admin)) -> dict:
    """Sube o cambia fotos del plato (desde arriba, frente, perfil). Con
    carta_video gasta cupo (primera foto = nuevo; si ya tenia = cambio; otra
    vez dentro de 30 min = el mismo cambio) y deja en la cola el clip."""
    dish = await _dish(db, company_id, item_id)
    files = {"top": await _read_upload(top), "front": await _read_upload(front), "side": await _read_upload(side)}
    if not any(files.values()):
        raise HTTPException(status_code=422, detail="Elige una foto.")
    cid = str(company_id)
    current = await mv.dish_media(db, cid, dish["id"])
    had = bool(current and any(current.get(f"{r}_original") for r in mv.ROLES))
    video = await mv.video_on(db, cid)
    try:
        if video:
            await mv.spend(db, cid, "cambio" if had else "nuevo", dish["id"], actor)
        for role in mv.ROLES:
            if files[role]:
                raw, name = files[role]
                await mv.save_photo(db, cid, dish["id"], role, raw, name)
        if video:
            await mv.enqueue(db, cid, dish["id"], style)
        else:
            # carta simple: la foto se ve mejor y mas liviana con el mismo
            # remasterizado (sin IA, en la misma peticion); no hay clip.
            await _remaster_now(db, cid, dish["id"])
        await db.commit()
    except mv.QuotaExceeded as error:
        await db.rollback()
        raise _quota_error(error) from None
    except (mm.MediaRejected, brand_media.StorageUnavailable, brand_media.ImageRejected) as error:
        await db.rollback()
        raise _media_error(error) from None
    if video:
        mv.wake()
    changed = [ROLE_WORDS[r] for r in mv.ROLES if files[r]]
    await audit(request, cid, actor, plato=dish["name"], foto="cambió" if had else "subió", fotos=", ".join(changed))
    return await portal_state(db, company_id)


class RestoreIn(BaseModel):
    original: str = Field(..., max_length=40)
    remaster: str = Field(default="", max_length=40)


@router.delete("/companies/{company_id}/items/{item_id}/photo/{role}")
async def delete_role(company_id: uuid.UUID, item_id: uuid.UUID, role: str, request: Request, db: AsyncSession = Depends(get_db),
                      actor: str = Depends(require_carta_admin)) -> dict:
    """Quita UNA foto (no gasta cupo). El clip se rehace con las que queden; sin
    ninguna, el QR muestra la tarjeta del plato. Devuelve `undo` (10 s)."""
    dish = await _dish(db, company_id, item_id)
    cid = str(company_id)
    try:
        undo = await mv.remove_role(db, cid, dish["id"], role)
        if not undo["empty"] and await mv.video_on(db, cid):
            await mv.enqueue(db, cid, dish["id"], "auto")
        await db.commit()
    except brand_media.ImageRejected as error:
        await db.rollback()
        raise _media_error(error) from None
    mv.wake()
    await audit(request, cid, actor, plato=dish["name"], foto="quitó", fotos=ROLE_WORDS.get(role, role))
    return {**await portal_state(db, company_id), "undo": undo}


@router.post("/companies/{company_id}/items/{item_id}/photo/{role}/restore")
async def restore_role(company_id: uuid.UUID, item_id: uuid.UUID, role: str, payload: RestoreIn, request: Request,
                       db: AsyncSession = Depends(get_db), actor: str = Depends(require_carta_admin)) -> dict:
    """Deshacer "Quitar" (el archivo seguia guardado). No gasta cupo."""
    dish = await _dish(db, company_id, item_id)
    cid = str(company_id)
    try:
        await mv.restore_role(db, cid, dish["id"], role, payload.original, payload.remaster)
        if await mv.video_on(db, cid):
            await mv.enqueue(db, cid, dish["id"], "auto")
        else:
            await _remaster_now(db, cid, dish["id"])
        await db.commit()
    except brand_media.ImageRejected as error:
        await db.rollback()
        raise _media_error(error) from None
    mv.wake()
    await audit(request, cid, actor, plato=dish["name"], foto="deshizo quitar", fotos=ROLE_WORDS.get(role, role))
    return await portal_state(db, company_id)


async def _remaster_now(db: AsyncSession, company_id: str, dish_ref: str) -> None:
    media = await mv.dish_media(db, company_id, dish_ref) or {}
    for role in mv.ROLES:
        original_id = media.get(f"{role}_original")
        if not original_id or media.get(f"{role}_remaster"):
            continue
        row = await mv.asset(db, company_id, original_id)
        image = mm.load(await mv.read_bytes(row))
        result = mm.remaster(image)
        remaster_id = await mv.store_asset(db, company_id, dish_ref, role, "remaster", result.data, "image/webp",
                                           result.width, result.height)
        await mv.upsert_media(db, company_id, dish_ref, **{f"{role}_remaster": remaster_id})


@router.delete("/companies/{company_id}/items/{item_id}/photo")
async def delete_photo(company_id: uuid.UUID, item_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db),
                       actor: str = Depends(require_carta_admin)) -> dict:
    """Quita todas las fotos (y el video) del plato. No gasta cupo."""
    dish = await _dish(db, company_id, item_id)
    try:
        await mv.remove_photos(db, str(company_id), dish["id"])
        await db.commit()
    except brand_media.StorageUnavailable as error:
        await db.rollback()
        raise _media_error(error) from None
    await audit(request, str(company_id), actor, plato=dish["name"], foto="quitó", fotos="todas")
    return await portal_state(db, company_id)


class RedoIn(BaseModel):
    style: str = Field(default="auto", max_length=20)


@router.post("/companies/{company_id}/items/{item_id}/redo")
async def redo_clip(company_id: uuid.UUID, item_id: uuid.UUID, payload: RedoIn, db: AsyncSession = Depends(get_db),
                    _a: str = Depends(require_carta_admin)) -> dict:
    """Rehacer el clip con otro estilo (mismas fotos): no gasta cupo."""
    dish = await _dish(db, company_id, item_id)
    if not await mv.video_on(db, str(company_id)):
        raise HTTPException(status_code=403, detail="La carta en video no está activa para esta empresa.")
    media = await mv.dish_media(db, str(company_id), dish["id"])
    if not media or not any(media.get(f"{r}_original") for r in mv.ROLES):
        raise HTTPException(status_code=422, detail="Primero sube una foto.")
    await mv.enqueue(db, str(company_id), dish["id"], payload.style)
    await db.commit()
    mv.wake()
    return await portal_state(db, company_id)


class ChooseIn(BaseModel):
    use_remaster: bool = True


@router.post("/companies/{company_id}/items/{item_id}/choose")
async def choose_version(company_id: uuid.UUID, item_id: uuid.UUID, payload: ChooseIn, db: AsyncSession = Depends(get_db),
                         _a: str = Depends(require_carta_admin)) -> dict:
    """Antes/despues: usar la remasterizada o la original. No gasta cupo."""
    dish = await _dish(db, company_id, item_id)
    cid = str(company_id)
    media = await mv.dish_media(db, cid, dish["id"])
    if not media:
        raise HTTPException(status_code=422, detail="El plato no tiene foto.")
    await mv.upsert_media(db, cid, dish["id"], use_remaster=payload.use_remaster)
    video = await mv.video_on(db, cid)
    if video:
        await mv.enqueue(db, cid, dish["id"], media.get("clip_style") or "auto")
    await db.commit()
    if video:
        mv.wake()
    return await portal_state(db, company_id)


class QuotaRequestIn(BaseModel):
    detalle: str = Field(default="", max_length=300)


@router.post("/companies/{company_id}/quota/request")
async def request_more_quota(company_id: uuid.UUID, payload: QuotaRequestIn, request: Request,
                             db: AsyncSession = Depends(get_db), actor: str = Depends(require_carta_admin)) -> dict:
    """"Solicitar mas": queda en el registro y avisa al equipo por n8n
    (Telegram y Gmail). Si n8n no responde, la solicitud igual queda."""
    cid = str(company_id)
    if not await mv.video_on(db, cid):
        raise HTTPException(status_code=403, detail="La carta en video no está activa para esta empresa.")
    company = (await db.execute(text("SELECT name FROM companies WHERE id = CAST(:c AS uuid)"), {"c": cid})).mappings().first()
    state = await mv.quota_state(db, cid)
    detail = mv.clean(payload.detalle, 300) or "Más cupo de platos nuevos y cambios de foto/video"
    await mv.log_request(db, cid, detail, actor)
    await db.commit()
    base = str(request.base_url).rstrip("/").replace("http://", "https://", 1)
    sent, why = await mv.call_n8n(mv.quota_webhook_url(), {
        "empresa": (company or {}).get("name") or "", "company_id": cid, "pidio": detail, "por": actor,
        "mes": state["month"], "nuevos": state["new"], "cambios": state["changes"],
        "ficha_url": f"{base}/admin-v2plus#empresa/{cid}",
    }, timeout=10.0)
    return {"ok": True, "notified": sent, "message": "Te contactaremos para ampliar tu plan.", **({"detail": why} if not sent else {})}


# ------------------------------------------------- carta QR de la mesa ---
class TableIn(BaseModel):
    table: str = Field(default="Mesa", max_length=120)
    access_code: str = Field(default="", max_length=12)


@router.post("/qr/{company_id}/carta")
async def table_carta(company_id: uuid.UUID, payload: TableIn, db: AsyncSession = Depends(get_db)) -> dict:
    """057C: la carta nueva para el QR de la mesa. La credencial es la clave
    de la mesa activa (la misma que exige el envio del pedido)."""
    from app.api.v1.endpoints import hospitality as hsp
    from app.api.v1.endpoints.carta import carta_enabled
    from app.services import carta_app

    await hsp._require_table_access(db, company_id, payload.table or "Mesa", payload.access_code)
    if not await carta_enabled(db, company_id):
        raise HTTPException(status_code=404, detail="Esta empresa no usa la Carta.")
    return {**await carta_app.payload(db, company_id), "table": payload.table}


# ------------------------------------------------------- regreso de n8n ---
def require_carta_token(request: Request) -> None:
    expected = mv.token()
    if not expected:
        raise HTTPException(status_code=503, detail="import_not_configured")
    given = (request.headers.get("x-carta-token") or "").strip()
    if not given or not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="invalid_token")


class _Sub(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nombre: str = Field(..., min_length=1, max_length=200)


class _Category(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nombre: str = Field(..., min_length=1, max_length=200)
    subcategorias: list[_Sub] = Field(default_factory=list, max_length=80)


class _Dish(BaseModel):
    model_config = ConfigDict(extra="ignore")
    categoria: str = Field(default="", max_length=200)
    subcategoria: Optional[str] = Field(default="", max_length=200)
    nombre: str = Field(..., min_length=1, max_length=300)
    descripcion: Optional[str] = Field(default="", max_length=2000)
    precio: Any = None
    opciones: Any = None

    @field_validator("subcategoria", "descripcion", mode="before")
    @classmethod
    def _none_is_empty(cls, value: Any) -> Any:
        return "" if value is None else value


class CallbackIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    job_id: uuid.UUID
    company_id: uuid.UUID
    categorias: list[_Category] = Field(default_factory=list, max_length=80)
    platos: list[_Dish] = Field(default_factory=list, max_length=500)
    error: Optional[str] = Field(default=None, max_length=600)


@router.post("/import-callback", dependencies=[Depends(require_carta_token)])
async def import_callback(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="invalid_json") from None
    if isinstance(body, dict) and isinstance(body.get("resultado"), dict):
        body = {**body, **body["resultado"]}
    try:
        payload = CallbackIn.model_validate(body)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=[{"loc": e.get("loc"), "msg": e.get("msg")} for e in error.errors()[:10]]) from None
    current = await mv.get_import(db, payload.company_id, payload.job_id)
    if not current:
        raise HTTPException(status_code=404, detail="import_not_found")
    if current["status"] == "publicada":
        raise HTTPException(status_code=409, detail="import_already_published")
    if payload.error or not payload.platos:
        await mv.mark_import(db, payload.company_id, payload.job_id, "error",
                             payload.error or "No se encontraron platos en la carta. Llénala a mano.")
        await db.commit()
        return {"ok": True, "status": "error"}
    table = await mv.save_table(db, payload.company_id, payload.job_id, payload.model_dump(mode="json"), status="lista", error=None)
    await db.commit()
    return {"ok": True, "status": "lista", "categorias": len(table["categorias"]), "platos": len(table["platos"])}
