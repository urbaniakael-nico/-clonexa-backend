"""Nexa por WhatsApp (API oficial de Meta): webhook de Meta y registro de n8n.

Ninguna ruta es abierta; cada una exige su credencial en el servidor:
- GET  /webhook: verificacion de Meta (hub.verify_token = WA_VERIFY_TOKEN).
- POST /webhook: firma X-Hub-Signature-256 con META_APP_SECRET (mala -> 401).
  Responde 200 de inmediato y procesa en segundo plano (app/services/nexa_whatsapp.py).
- POST /outbound y GET /daily-summary: los llama n8n con X-Nexa-Forward =
  NEXA_WA_FORWARD_SECRET.
Sin la variable, 503. Nunca se registra ni se devuelve un secreto: el log de
acceso de uvicorn tapa hub.verify_token (RedactVerifyToken).
La consola (solo Admin V2) vive en app/web/nexa_wa_routes.py.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import nexa_whatsapp as nw

router = APIRouter()
log = logging.getLogger("clonexa.nexa_wa")

MAX_BODY = 1_000_000
SESSION_FACTORY = None  # las pruebas lo cambian; por defecto la sesion de la app
SERVICE_PER_IP = nw.RateLimit(240, 60.0)

_TOKEN_IN_QUERY = re.compile(r"(hub[._]verify_token=)[^&\s\"]*", re.I)


class RedactVerifyToken(logging.Filter):
    """El log de acceso de uvicorn imprime la URL completa: la verificacion de
    Meta llevaba el token de verificacion en claro. Se reemplaza por ***."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.args, tuple) and record.args:
                record.args = tuple(_TOKEN_IN_QUERY.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
            if isinstance(record.msg, str) and "verify_token" in record.msg:
                record.msg = _TOKEN_IN_QUERY.sub(r"\1***", record.msg)
        except Exception:  # noqa: BLE001 - un filtro de log nunca tumba nada
            pass
        return True


_access = logging.getLogger("uvicorn.access")
if not any(isinstance(f, RedactVerifyToken) for f in _access.filters):
    _access.addFilter(RedactVerifyToken())


def _session_factory():
    if SESSION_FACTORY is not None:
        return SESSION_FACTORY
    from app.core.database import AsyncSessionLocal
    return AsyncSessionLocal


def _ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    return (forwarded.split(",")[0].strip() or (request.client.host if request.client else "") or "?")[:64]


def require_forward(request: Request) -> None:
    """n8n -> backend. El orden importa: limite, variable, secreto."""
    if not SERVICE_PER_IP.allow(_ip(request)):
        raise HTTPException(status_code=429, detail="too_many_requests")
    expected = nw.env("NEXA_WA_FORWARD_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="not_configured")
    if not nw.same_secret((request.headers.get("x-nexa-forward") or "").strip(), expected):
        raise HTTPException(status_code=401, detail="invalid_token")


# ---------------------------------------------------------------- Meta
@router.get("/webhook", include_in_schema=False)
async def verify(hub_mode: str = Query(default="", alias="hub.mode"), hub_token: str = Query(default="", alias="hub.verify_token"),
                 hub_challenge: str = Query(default="", alias="hub.challenge")):
    expected = nw.env("WA_VERIFY_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="not_configured")
    if hub_mode != "subscribe" or not nw.same_secret(hub_token, expected):
        raise HTTPException(status_code=403, detail="forbidden")
    return PlainTextResponse(hub_challenge[:200])


async def run_webhook(payload: dict) -> None:
    try:
        async with _session_factory()() as db:
            await nw.process_webhook(db, payload)
    except Exception as exc:  # segundo plano: se registra, se avisa y no tumba nada
        log.exception("nexa_wa error: no se pudo procesar el webhook")
        await nw.alert("no se pudo procesar el webhook (base de datos?)", type(exc).__name__)


@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request, background: BackgroundTasks):
    secret = nw.env("META_APP_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="not_configured")
    body = await request.body()
    log.info("nexa_wa recibido bytes=%s ip=%s", len(body), _ip(request))
    if len(body) > MAX_BODY:
        log.warning("nexa_wa rechazado: cuerpo de %s bytes", len(body))
        raise HTTPException(status_code=413, detail="too_large")
    if not nw.signature_ok(body, request.headers.get("x-hub-signature-256") or "", secret):
        log.warning("nexa_wa firma_mala ip=%s (cabecera %s)", _ip(request), "presente" if request.headers.get("x-hub-signature-256") else "ausente")
        raise HTTPException(status_code=401, detail="invalid_signature")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        log.warning("nexa_wa json_malo")
        raise HTTPException(status_code=400, detail="invalid_json") from None
    log.info("nexa_wa firma_ok")
    background.add_task(run_webhook, payload)
    return {"ok": True}


# ---------------------------------------------------------------- n8n
Tipo = Literal["text", "buttons", "list"]
Etapa = Literal["nuevo", "calificado", "demo_agendada", "pidio_persona", "no_interesado", "baja"]


class _Msg(BaseModel):
    model_config = ConfigDict(extra="ignore")
    meta_id: Optional[str] = Field(default=None, max_length=200)
    tipo: Tipo = "text"
    texto: str = Field(default="", max_length=4096)
    opciones: list[str] = Field(default_factory=list, max_length=10)
    estado: Optional[Literal["sent", "delivered", "read", "failed"]] = None
    error: Optional[str] = Field(default=None, max_length=500)


class _Datos(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nombre: Optional[str] = None
    idioma: Optional[str] = None
    tipo_negocio: Optional[str] = None
    ciudad: Optional[str] = None
    tamano: Optional[str] = None
    dolor: Optional[str] = None
    correo: Optional[str] = None


class _Demo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    inicio: Optional[str] = Field(default=None, max_length=40, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
    enlace: Optional[str] = Field(default=None, max_length=500)


class OutboundIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # telefono (digitos) o id de usuario de WhatsApp sin telefono (BSUID, p. ej. "CO.1234...")
    wa_id: str = Field(min_length=5, max_length=32, pattern=r"^(\d+|[A-Z]{2}\.[A-Za-z0-9_-]+)$")
    mensajes: list[_Msg] = Field(default_factory=list, max_length=10)
    datos_detectados: _Datos = Field(default_factory=_Datos)
    etapa: Optional[Etapa] = None
    consentimiento_visto: bool = False
    accion: Optional[str] = Field(default=None, max_length=40)
    demo: Optional[_Demo] = None
    nota: Optional[str] = Field(default=None, max_length=1000)


@router.post("/outbound", include_in_schema=False)
async def outbound(body: OutboundIn, _: None = Depends(require_forward), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    contact = await nw.contact_by_wa(db, body.wa_id)
    if not contact:
        raise HTTPException(status_code=404, detail="contact_not_found")
    data = body.model_dump()
    data["mensajes"] = [m for m in data["mensajes"] if (m.get("texto") or "").strip() or m.get("meta_id")]
    updated = await nw.record_outbound(db, contact, data)
    return {"ok": True, "contacto": nw.contact_public(updated), "etapa_label": nw.STAGE_LABELS.get(updated["stage"], updated["stage"])}


@router.get("/daily-summary", include_in_schema=False)
async def daily_summary(_: None = Depends(require_forward), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await nw.daily_summary(db)
