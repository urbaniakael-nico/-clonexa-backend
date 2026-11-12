"""Prospeccion por ubicacion de Nexa (interno de Clonexa: sin company_id; no es de ninguna empresa).

Autenticacion (todo validado en el servidor):
- /n8n/*    : token de servicio de n8n (cabecera X-Nexa-Token = NEXA_INGEST_TOKEN, tiempo constante).
              Sin la variable 503, token mal 401. Limite propio de 600 por minuto por IP.
- /admin/*  : sesion activa de Admin V2 (consola v2+). Sin sesion 401.
- /baja     : el enlace "No quiero recibir más correos" del correo. Lo abre el negocio sin cuenta
              (obligatorio por ley): se autentica con un token aleatorio de 32 caracteres propio de cada
              prospecto (unsub_token). Solo puede dar de baja a ESE negocio; no lee ni devuelve datos.
- /vista-previa/{lote}: el boton "Ver correo de ejemplo" de Telegram. Token aleatorio del lote, vence a
              los 2 dias. Solo muestra el primer correo del lote.
"""
from __future__ import annotations

import hmac
import os
import re
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.social_metrics import _ip, _RateLimit, require_admin_v2_session
from app.services import prospecting as ps
from app.services import prospecting_email as pe

router = APIRouter()
TOKEN_ENV = "NEXA_INGEST_TOKEN"
N8N_PER_IP = _RateLimit(600, 60.0)
PUBLIC_PER_IP = _RateLimit(30, 60.0)
NO_STORE = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex"}


def require_n8n(request: Request) -> None:
    if not N8N_PER_IP.allow(_ip(request)):
        raise HTTPException(status_code=429, detail="too_many_requests")
    expected = os.getenv(TOKEN_ENV, "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="not_configured")
    given = (request.headers.get("x-nexa-token") or "").strip()
    if not given or not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="invalid_token")


n8n = [Depends(require_n8n)]
admin = [Depends(require_admin_v2_session)]


# ---------------------------------------------------------------- n8n: prospeccion
@router.get("/n8n/scan-plan", dependencies=n8n)
async def scan_plan(max: int = Query(default=12, ge=1, le=40), zona: str = Query(default="", max_length=60),
                    tipos: str = Query(default="", max_length=200), nicho: str = Query(default="", max_length=20),
                    forzar: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    types = [t for t in tipos.split(",") if t] or None
    return {"plan": await ps.scan_plan(db, max_searches=max, zone_slug=zona, types=types, force=forzar,
                                       niche=nicho if nicho in ps.NICHES else "")}


class PlacesIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    zone_id: int
    business_type: str = Field(max_length=30)
    places: list[dict] = Field(default_factory=list, max_length=60)
    next_page_token: str = Field(default="", max_length=2000)
    limit_new: Optional[int] = Field(default=None, ge=0, le=60)
    scan_web: bool = True


@router.post("/n8n/places", dependencies=n8n)
async def ingest_places(body: PlacesIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        out = await ps.ingest_places(db, zone_id=body.zone_id, business_type=body.business_type, places=body.places,
                                     next_page_token=body.next_page_token, limit_new=body.limit_new, scan_web=body.scan_web)
    except LookupError:
        raise HTTPException(status_code=404, detail="zona_no_existe") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    out.pop("new_ids", None)
    return {"ok": True, **out}


@router.get("/n8n/scan-report", dependencies=n8n)
async def scan_report(desde: str = Query(default="", max_length=40), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        since = datetime.fromisoformat(desde.replace("Z", "+00:00")) if desde else ps.now() - timedelta(hours=12)
    except ValueError:
        raise HTTPException(status_code=422, detail="fecha_invalida") from None
    if since.tzinfo is None:
        since = since.replace(tzinfo=ps.BOGOTA)
    rep = await ps.scan_report(db, since)
    lines = [f"🔎 <b>Prospección de hoy</b>: {rep['nuevos']} negocios nuevos ({rep['nuevos_con_correo']} con correo publicado)"]
    lines += [f"• {r['zona']}: {r['nuevos']} ({r['con_correo']} con correo)" for r in rep["zonas"]]
    if rep.get("nichos"):
        lines.append("\nPor nicho:")
        lines += [f"• {_esc(n['label'])}: {n['nuevos']} · correo {n['con_correo']} · IG/FB {n['con_redes']} · WhatsApp publicado "
                  f"{n['con_whatsapp']} · por verificar {n['por_verificar']}" for n in rep["nichos"]]
    lines.append(f"\nEn la lista: {rep['total']} prospectos, {rep['total_con_correo']} con correo.")
    return {**rep, "mensaje": "\n".join(lines)}


@router.get("/n8n/refresh-due", dependencies=n8n)
async def refresh_due(limit: int = Query(default=40, ge=1, le=200), db: AsyncSession = Depends(get_db)) -> dict:
    return {"items": await ps.refresh_due(db, limit), "field_mask": ps.DETAIL_FIELD_MASK}


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prospect_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    place: Optional[dict] = None
    not_found: bool = False


@router.post("/n8n/refresh", dependencies=n8n)
async def refresh(body: RefreshIn, db: AsyncSession = Depends(get_db)) -> dict:
    place = body.place if body.place and not body.place.get("error") else None
    return await ps.apply_refresh(db, body.prospect_id, place, not_found=body.not_found or place is None)


# ---------------------------------------------------------------- n8n: lote y envio
def _batch_message(view: dict, preview_url: str) -> str:
    b, items = view["batch"], view["items"]
    lines = [f"📬 <b>Lote de correos de hoy</b> ({b['local_date']}): {len(items)} negocios"]
    for i, it in enumerate(items, 1):
        tag = " · seguimiento" if it["kind"] == "seguimiento" else ""
        lines.append(f"{i}. {_esc(it['name'])} · {_esc(it['zona'] or '')} · {_esc(it['tipo'])} · {_esc(it['to_email'])}{tag}")
    lines.append("\nSe envían espaciados entre 8:00 y 17:00. Nada sale sin tu ✅.")
    return "\n".join(lines)[:4000]


def _esc(v: Any) -> str:
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _preview_url(request: Request, cfg: dict, b: dict) -> str:
    base = (cfg.get("backend_url") or str(request.base_url)).rstrip("/")
    return f"{base}/api/v1/prospecting/vista-previa/{b['id']}?t={b['preview_token']}"


@router.post("/n8n/batch/today", dependencies=n8n)
async def batch_today(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    view = await ps.build_batch(db)
    if not view.get("batch"):
        return {"ok": True, "batch": None, "items": [], "motivo": view.get("motivo", ""), "enviar_aviso": False}
    cfg = await ps.get_settings(db)
    b = view["batch"]
    url = _preview_url(request, cfg, b)
    return {"ok": True, "batch": {k: b[k] for k in ("id", "local_date", "status", "item_count")}, "items": view["items"],
            "preview_url": url, "mensaje": _batch_message(view, url), "enviar_aviso": b["status"] == "pendiente"}


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    accion: Literal["enviar", "saltar"]


@router.post("/n8n/batch/{batch_id}/decide", dependencies=n8n)
async def batch_decide(batch_id: int, body: DecideIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        view = await ps.decide_batch(db, batch_id, approve=body.accion == "enviar")
    except LookupError:
        raise HTTPException(status_code=404, detail="lote_no_existe") from None
    except ValueError as exc:
        return {"ok": False, "motivo": str(exc), "mensaje": "⚠️ Ese lote es de otro día: ya no se puede aprobar."}
    st = view["batch"]["status"]
    n = len([i for i in view["items"] if i["status"] in ("aprobado", "enviando", "enviado")])
    texto = {"aprobado": f"✅ LOTE APROBADO: {n} correos salen espaciados hoy entre 8:00 y 17:00.",
             "saltado": "❌ Lote saltado: hoy no sale ningún correo (los negocios quedan para otro día)."}.get(st, f"Lote: {st}")
    if not view.get("cambio"):
        texto = f"Este lote ya estaba {st}."
    return {"ok": True, "status": st, "mensaje": texto}


@router.post("/n8n/outbox/claim", dependencies=n8n)
async def outbox_claim(db: AsyncSession = Depends(get_db)) -> dict:
    return await ps.claim_next(db)


class SentIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_id: str = Field(default="", max_length=200)
    thread_id: str = Field(default="", max_length=200)
    error: str = Field(default="", max_length=500)


@router.post("/n8n/outbox/{contact_id}/sent", dependencies=n8n)
async def outbox_sent(contact_id: int, body: SentIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return await ps.mark_sent(db, contact_id, message_id=body.message_id, thread_id=body.thread_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="no_existe") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/n8n/outbox/{contact_id}/failed", dependencies=n8n)
async def outbox_failed(contact_id: int, body: SentIn, db: AsyncSession = Depends(get_db)) -> dict:
    return await ps.mark_failed(db, contact_id, body.error)


@router.post("/n8n/test-emails", dependencies=n8n)
async def test_emails(db: AsyncSession = Depends(get_db)) -> dict:
    """Correos de ejemplo de las 3 plantillas: SIEMPRE al correo de Clonexa (nunca a un negocio)."""
    from app.web.admin_v2_routes import ADMIN_V2_EMAIL

    cfg = await ps.get_settings(db)
    recipient = (cfg.get("test_recipient") or ADMIN_V2_EMAIL or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", recipient):
        raise HTTPException(status_code=409, detail="sin_correo_de_prueba")
    return {"items": await ps.test_emails(db, recipient)}


class InboundIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    de: str = Field(default="", max_length=320)
    asunto: str = Field(default="", max_length=500)
    cuerpo: str = Field(default="", max_length=8000)
    thread_id: str = Field(default="", max_length=200)


@router.post("/n8n/inbound-email", dependencies=n8n)
async def inbound_email(body: InboundIn, db: AsyncSession = Depends(get_db)) -> dict:
    out = await ps.inbound_email(db, sender=body.de, subject=body.asunto, body=body.cuerpo, thread_id=body.thread_id)
    p = out.get("prospecto")
    aviso = ""
    if p:
        if out["baja"]:
            aviso = f"🚫 <b>{_esc(p['name'])}</b> ({_esc(p['zone_name'])}) respondió que NO: quedó de baja y no recibe nada más."
        else:
            aviso = (f"🎯 <b>{_esc(p['name'])}</b> respondió el correo de prospección ({_esc(p['tipo'])}, {_esc(p['zone_name'])}).\n"
                     f"Correo: {_esc(p['email'])}\nRevísalo en Gmail y en el Mapa comercial.")
    return {**out, "es_prospecto": bool(p), "aviso": aviso}


# ---------------------------------------------------------------- publicos con token
@router.get("/baja", include_in_schema=False)
async def unsubscribe_link(request: Request, t: str = Query(default="", max_length=80), db: AsyncSession = Depends(get_db)):
    if not PUBLIC_PER_IP.allow(_ip(request)):
        raise HTTPException(status_code=429, detail="too_many_requests")
    p, changed = await ps.unsubscribe_by_token(db, t)
    if not p:
        return HTMLResponse(pe.invalid_link_page(), status_code=404, headers=NO_STORE)
    return HTMLResponse(pe.unsubscribed_page(p["name"], already=not changed), headers=NO_STORE)


@router.post("/baja", include_in_schema=False)
async def unsubscribe_one_click(request: Request, t: str = Query(default="", max_length=80), db: AsyncSession = Depends(get_db)):
    """List-Unsubscribe-Post (RFC 8058): baja con un clic desde el cliente de correo."""
    if not PUBLIC_PER_IP.allow(_ip(request)):
        raise HTTPException(status_code=429, detail="too_many_requests")
    p, _ = await ps.unsubscribe_by_token(db, t, source="un_clic")
    if not p:
        raise HTTPException(status_code=404, detail="enlace_invalido")
    return {"ok": True}


@router.get("/vista-previa/{batch_id}", include_in_schema=False)
async def batch_preview(request: Request, batch_id: int, t: str = Query(default="", max_length=80), db: AsyncSession = Depends(get_db)):
    if not PUBLIC_PER_IP.allow(_ip(request)):
        raise HTTPException(status_code=429, detail="too_many_requests")
    page = await ps.preview_html(db, batch_id, t)
    if not page:
        return HTMLResponse(pe.invalid_link_page(), status_code=404, headers=NO_STORE)
    return HTMLResponse(page, headers=NO_STORE)


# ---------------------------------------------------------------- consola v2+ (Admin V2)
@router.get("/admin/map", dependencies=admin)
async def admin_map(zone_id: Optional[int] = None, tipo: str = Query(default="", max_length=30), nicho: str = Query(default="", max_length=20),
                    vigencia: str = Query(default="", max_length=16),
                    estado: str = Query(default="", max_length=20), desde: str = Query(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$"),
                    hasta: str = Query(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$"), db: AsyncSession = Depends(get_db)) -> dict:
    from app.api.v1.endpoints import landing_analytics

    await landing_analytics._ensure_storage(db)
    await landing_analytics.backfill_geo(db)
    data = await ps.map_data(db, {"zone_id": zone_id, "type": tipo, "niche": nicho, "vigencia": vigencia, "status": estado, "desde": desde, "hasta": hasta})
    return {**data, "attribution": {"map": "© OpenStreetMap", "ip": "IP Geolocation by DB-IP", "ip_url": "https://db-ip.com"}}


@router.get("/admin/prospects/{prospect_id}", dependencies=admin)
async def admin_prospect(prospect_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    if not re.fullmatch(r"[0-9a-f-]{36}", prospect_id):
        raise HTTPException(status_code=404, detail="no_existe")
    # Solo Admin V2 llega aqui (dependencia): el correo completo se muestra en la ficha; en el mapa va oculto.
    d = await ps.prospect_detail(db, prospect_id, full_email=True)
    if not d:
        raise HTTPException(status_code=404, detail="no_existe")
    return d


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    estado: Literal["demo", "cliente", "baja"]


@router.post("/admin/prospects/{prospect_id}/status", dependencies=admin)
async def admin_prospect_status(prospect_id: str, body: StatusIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"ok": True, "prospect": await ps.set_status(db, prospect_id, body.estado)}
    except LookupError:
        raise HTTPException(status_code=404, detail="no_existe") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


class ZoneIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=2, max_length=120)
    group_name: str = Field(default="", max_length=120)
    city: str = Field(default="Bogotá", max_length=80)
    center_lat: float = Field(ge=-4.5, le=13.5)   # Colombia
    center_lng: float = Field(ge=-82.0, le=-66.0)
    radius_m: int = Field(default=700, ge=150, le=5000)
    polygon: Optional[list[list[float]]] = Field(default=None, max_length=200)
    active: bool = True
    niches: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("polygon")
    @classmethod
    def _poly(cls, v):
        if v is not None and (len(v) < 3 or any(len(p) != 2 for p in v)):
            raise ValueError("poligono_invalido")
        return v


@router.get("/admin/zones", dependencies=admin)
async def admin_zones(db: AsyncSession = Depends(get_db)) -> dict:
    return {"zones": await ps.zones(db)}


@router.post("/admin/zones", dependencies=admin)
async def admin_zone_create(body: ZoneIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"ok": True, "zone": await ps.save_zone(db, body.model_dump())}
    except ValueError:
        raise HTTPException(status_code=409, detail="zona_repetida") from None


@router.put("/admin/zones/{zone_id}", dependencies=admin)
async def admin_zone_update(zone_id: int, body: ZoneIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"ok": True, "zone": await ps.save_zone(db, body.model_dump(), zone_id)}
    except LookupError:
        raise HTTPException(status_code=404, detail="zona_no_existe") from None


class ChainsIn(BaseModel):
    names: list[str] = Field(max_length=500)


@router.get("/admin/chains", dependencies=admin)
async def admin_chains(db: AsyncSession = Depends(get_db)) -> dict:
    return {"chains": [c["name"] for c in await ps.chains(db)]}


@router.put("/admin/chains", dependencies=admin)
async def admin_chains_save(body: ChainsIn, db: AsyncSession = Depends(get_db)) -> dict:
    return {"chains": [c["name"] for c in await ps.set_chains(db, body.names)]}


@router.get("/admin/niches", dependencies=admin)
async def admin_niches(db: AsyncSession = Depends(get_db)) -> dict:
    """Nichos con su pagina de la landing, prioridad, tipos que se buscan y cadenas excluidas del nicho."""
    nc = await ps.all_niche_chains(db)
    return {"niches": [{"key": k, **v, "types": ps.pn.types_of(k), "chains": nc.get(k, [])} for k, v in ps.NICHES.items()],
            "missing_pages": ps.pn.MISSING_PAGES}


@router.put("/admin/niches/{niche}/chains", dependencies=admin)
async def admin_niche_chains_save(niche: str, body: ChainsIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"niche": niche, "chains": await ps.set_niche_chains(db, niche, body.names)}
    except ValueError:
        raise HTTPException(status_code=404, detail="nicho_invalido") from None


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    daily_limit: Optional[int] = Field(default=None, ge=1, le=25)
    min_gap_minutes: Optional[int] = Field(default=None, ge=3, le=60)
    signature: Optional[str] = Field(default=None, max_length=120)
    sender_name: Optional[str] = Field(default=None, max_length=80)
    sender_email: Optional[str] = Field(default=None, max_length=200)
    reply_to: Optional[str] = Field(default=None, max_length=200)
    test_recipient: Optional[str] = Field(default=None, max_length=200)
    search_limits: Optional[dict[str, int]] = None
    zone_search_limit: Optional[int] = Field(default=None, ge=0, le=40)
    rescan_days: Optional[int] = Field(default=None, ge=6, le=90)
    assisted_daily_limit: Optional[int] = Field(default=None, ge=0, le=30)
    vigencia_months: Optional[int] = Field(default=None, ge=3, le=36)
    vigencia_min_reviews: Optional[int] = Field(default=None, ge=0, le=50)


@router.get("/admin/settings", dependencies=admin)
async def admin_settings(db: AsyncSession = Depends(get_db)) -> dict:
    return {"settings": await ps.get_settings(db)}


@router.put("/admin/settings", dependencies=admin)
async def admin_settings_save(body: SettingsIn, db: AsyncSession = Depends(get_db)) -> dict:
    return {"settings": await ps.save_settings(db, body.model_dump(exclude_none=True))}
