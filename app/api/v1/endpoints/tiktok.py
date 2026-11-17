"""Publicar en TikTok desde la consola v2+ (solo Admin V2) y callback OAuth via n8n.

/api/v1/tiktok/admin/*  -> sesion de Admin V2 (401 sin ella).
/api/v1/tiktok/n8n/*    -> autenticacion de servicio de n8n (X-Nexa-Token), como el resto de Nexa.
Nada se envia a TikTok sin que el usuario toque Publicar o Enviar como borrador en la pantalla.
Los tokens de TikTok nunca salen en las respuestas.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.prospecting import require_n8n
from app.api.v1.endpoints.social_metrics import require_admin_v2_session
from app.services import tiktok_posting as tt

logger = logging.getLogger(__name__)
router = APIRouter()
admin = [Depends(require_admin_v2_session)]
n8n = [Depends(require_n8n)]
NO_STORE = {"Cache-Control": "no-store"}


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, tt.TikTokError):
        logger.info("tiktok error codigo=%s", exc.code)   # solo el codigo: nunca tokens
        return HTTPException(status_code=exc.status, detail={"mensaje": tt.safe_message(exc), "codigo": exc.code})
    logger.warning("tiktok fallo inesperado %s: %s", type(exc).__name__, tt.safe_message(exc))
    return HTTPException(status_code=502, detail={"mensaje": "No se pudo hablar con TikTok. Intenta de nuevo.", "codigo": "network"})


def _console(request: Request, fragment: str) -> str:
    host = request.headers.get("x-forwarded-host") or request.url.hostname or ""
    return f"https://{host}/admin-v2plus#{fragment}"


# ------------------------------------------------------------------ admin
@router.get("/admin/estado", dependencies=admin)
async def estado(db: AsyncSession = Depends(get_db)) -> dict:
    return {"ok": True, **await tt.status(db)}


@router.post("/admin/conectar", dependencies=admin)
async def conectar(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"ok": True, "url": await tt.authorize_url(db)}
    except Exception as exc:
        raise _fail(exc) from None


@router.post("/admin/desconectar", dependencies=admin)
async def desconectar(db: AsyncSession = Depends(get_db)) -> dict:
    await tt.disconnect(db)
    return {"ok": True}


@router.get("/admin/creator", dependencies=admin)
async def creator(db: AsyncSession = Depends(get_db)) -> Response:
    try:
        info = await tt.creator_info(db)
    except Exception as exc:
        raise _fail(exc) from None
    import json

    return Response(json.dumps({"ok": True, **info}), media_type="application/json", headers=NO_STORE)


@router.get("/admin/piezas", dependencies=admin)
async def piezas(db: AsyncSession = Depends(get_db)) -> dict:
    return {"ok": True, "piezas": [tt.piece_view(p) for p in await tt.store_for(db).list_pieces()]}


@router.post("/admin/subir", dependencies=admin)
async def subir(file: UploadFile = File(...), tema: str = Form(""), caption: str = Form(""), db: AsyncSession = Depends(get_db)) -> dict:
    data = await file.read(tt.MAX_VIDEO_BYTES + 1)
    try:
        piece = await tt.save_piece(db, data, origen="subida", tema=tema or (file.filename or "Video subido"), caption=caption)
    except Exception as exc:
        raise _fail(exc) from None
    return {"ok": True, "pieza": tt.piece_view(piece)}


@router.get("/admin/piezas/{piece_id}/video", dependencies=admin)
async def video(piece_id: str, db: AsyncSession = Depends(get_db)) -> Response:
    if not re.fullmatch(r"[0-9a-f-]{36}", piece_id):
        raise HTTPException(status_code=404, detail="no_existe")
    piece = await tt.store_for(db).get_piece(piece_id)
    if not piece:
        raise HTTPException(status_code=404, detail="no_existe")
    return Response(tt.media_get(piece["storage_key"]), media_type="video/mp4", headers={**NO_STORE, "Content-Disposition": "inline"})


class PublicarIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pieza: str = Field(max_length=40)
    caption: str = Field(default="", max_length=4000)
    privacy_level: str = Field(default="", max_length=40)
    allow_comment: bool = False
    allow_duet: bool = False
    allow_stitch: bool = False
    disclosure: bool = False
    your_brand: bool = False
    branded_content: bool = False


@router.post("/admin/publicar", dependencies=admin)
async def publicar(body: PublicarIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"ok": True, **await tt.publish(db, body.pieza, body.model_dump())}
    except Exception as exc:
        raise _fail(exc) from None


class BorradorIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pieza: str = Field(max_length=40)


@router.post("/admin/borrador", dependencies=admin)
async def borrador(body: BorradorIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"ok": True, **await tt.publish(db, body.pieza, {}, draft=True)}
    except Exception as exc:
        raise _fail(exc) from None


@router.get("/admin/publicaciones", dependencies=admin)
async def publicaciones(db: AsyncSession = Depends(get_db)) -> dict:
    return {"ok": True, "publicaciones": [tt.post_view(p) for p in await tt.store_for(db).list_posts()]}


@router.get("/admin/publicaciones/{post_id}/estado", dependencies=admin)
async def estado_publicacion(post_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    if not re.fullmatch(r"[0-9a-f-]{36}", post_id):
        raise HTTPException(status_code=404, detail="no_existe")
    try:
        return {"ok": True, **await tt.post_status(db, post_id)}
    except Exception as exc:
        raise _fail(exc) from None


# ------------------------------------------------------------------ n8n
class CallbackIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str = Field(default="", max_length=2000)
    state: str = Field(default="", max_length=200)
    error: str = Field(default="", max_length=200)


@router.post("/n8n/callback", dependencies=n8n)
async def callback(body: CallbackIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """El webhook tiktok-callback de n8n pasa code+state; se responde a donde redirigir el navegador."""
    if body.error:
        return {"ok": False, "redirect": _console(request, "tiktok?error=cancelado")}
    try:
        await tt.exchange_code(db, body.code, body.state)
    except tt.TikTokError as exc:
        return {"ok": False, "redirect": _console(request, "tiktok?error=" + ("estado" if exc.code == "invalid_state" else "token"))}
    except Exception:
        return {"ok": False, "redirect": _console(request, "tiktok?error=token")}
    return {"ok": True, "redirect": _console(request, "tiktok?conectada=1")}


@router.post("/n8n/pieza", dependencies=n8n)
async def registrar_pieza(request: Request, file: UploadFile = File(...), fila: Optional[int] = Form(None), fecha: str = Form(""),
                          tema: str = Form(""), caption: str = Form(""), db: AsyncSession = Depends(get_db)) -> dict:
    """La vista previa de Telegram ("Mostrar pieza") sube el video de la pieza y recibe el enlace a la pantalla
    Publicar en TikTok con la pieza precargada. Nada se publica aqui."""
    data = await file.read(tt.MAX_VIDEO_BYTES + 1)
    try:
        piece = await tt.save_piece(db, data, origen="calendario", fila=fila, fecha=fecha, tema=tema, caption=caption)
    except tt.TikTokError as exc:
        raise HTTPException(status_code=400, detail=tt.safe_message(exc)) from None
    return {"ok": True, "id": piece["id"], "enlace": _console(request, "tiktok=" + piece["id"])}
