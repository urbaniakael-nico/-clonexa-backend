"""NEXUS · Radar de innovacion (interno de Clonexa: sin company_id).

Autenticacion (todo en el servidor):
- /n8n/*   : token de servicio de n8n (X-Nexa-Token = NEXA_INGEST_TOKEN), igual que la prospeccion. Sin token 401.
- /admin/* : sesion activa de Admin V2 (consola v2+). Sin sesion 401.
Una sola fuente: lo que cambia en Telegram (NEXUS) o en la consola queda aqui.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.prospecting import require_n8n
from app.api.v1.endpoints.social_metrics import require_admin_v2_session
from app.services import radar as rd
from app.services import radar_ai as ai

router = APIRouter()
n8n = [Depends(require_n8n)]
admin = [Depends(require_admin_v2_session)]
State = Literal["nueva", "me_interesa", "backlog", "en_curso", "hecha", "descartada"]


# ---------------------------------------------------------------- n8n
class StartIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tipo: Literal["semanal", "a_pedido"] = "semanal"
    tema: str = Field(default="", max_length=300)
    origen: Literal["cron", "telegram", "consola"] = "cron"


@router.post("/n8n/start", dependencies=n8n)
async def n8n_start(body: StartIn, db: AsyncSession = Depends(get_db)) -> dict:
    """Abre el informe y devuelve la peticion completa para Claude (el prompt vive en el repo: app/services/radar_ai.py)."""
    out = await rd.start_report(db, tipo=body.tipo, tema=body.tema, origen=body.origen)
    if not out.get("ok"):
        return out
    excluded = [r["titulo"] for r in await rd.recent_titles(db)]
    req = ai.build_request(tipo=out["tipo"], tema=body.tema, temas=await rd.temas(db, active_only=True), excluded=excluded,
                           n=out["n"], hoy=rd.today())
    return {**out, "request": req}


class FinishIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    informe_id: int = Field(ge=1)
    request: dict = Field(default_factory=dict)
    responses: list[dict] = Field(default_factory=list, max_length=3)


@router.post("/n8n/continue", dependencies=n8n)
async def n8n_continue(body: FinishIn) -> dict:
    """pause_turn: la peticion para que Claude termine (se reenvia lo que ya hizo)."""
    return {"request": ai.continuation(body.request, body.responses[-1] if body.responses else {})}


@router.post("/n8n/finish", dependencies=n8n)
async def n8n_finish(body: FinishIn, db: AsyncSession = Depends(get_db)) -> dict:
    """Valida lo que trajo Claude (fuente real con fecha, sin repetir), guarda y arma los mensajes para NEXUS."""
    inf = await rd._one(db, "SELECT id, tipo, tema, estado FROM radar_informes WHERE id = :i", {"i": body.informe_id})
    if not inf or inf["estado"] != "corriendo":
        return {"ok": False, "mensaje": "⚠️ NEXUS: ese informe ya estaba cerrado."}
    err = ai.api_error(body.responses)
    usage = ai.usage_of(body.responses)
    if err:
        await rd.fail_report(db, body.informe_id, err)
        return {"ok": False, "mensaje": f"⚠️ NEXUS: el informe #{body.informe_id} falló: {rd.esc(err)}."}
    data = ai.parse_json(ai.final_text(body.responses))
    if data is None:
        await rd.fail_report(db, body.informe_id, "respuesta sin JSON")
        return {"ok": False, "mensaje": f"⚠️ NEXUS: el informe #{body.informe_id} falló: Claude no devolvió el JSON."}
    valid, discarded = ai.validate(data, ai.search_urls(body.responses))
    saved = await rd.save_report(db, body.informe_id, valid, discarded=discarded, usage=usage)
    items = [rd.telegram_item(await rd.idea(db, i)) for i in saved["ids"]]
    return {"ok": True, "cabecera": ai.header(inf["tipo"], inf["tema"], len(items), discarded + saved["repetidas"], usage["costo_usd"]),
            "ideas": items, "costo_usd": usage["costo_usd"], "descartadas": discarded, "repetidas": saved["repetidas"]}


class FailIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    informe_id: int = Field(default=0, ge=0)   # 0 = el que este corriendo (lo usa el flujo de errores)
    error: str = Field(default="", max_length=500)


@router.post("/n8n/fail", dependencies=n8n)
async def n8n_fail(body: FailIn, db: AsyncSession = Depends(get_db)) -> dict:
    iid = body.informe_id
    if not iid:
        row = await rd._one(db, "SELECT id FROM radar_informes WHERE estado = 'corriendo' ORDER BY id DESC LIMIT 1")
        iid = row["id"] if row else 0
    if iid:
        await rd.fail_report(db, iid, body.error)
    return {"ok": True, "mensaje": f"⚠️ NEXUS: el informe{f' #{iid}' if iid else ''} falló ({rd.esc(body.error[:120]) or 'error'})."}


class StateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    estado: State


@router.post("/n8n/ideas/{idea_id}/state", dependencies=n8n)
async def n8n_idea_state(idea_id: int, body: StateIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        i = await rd.update_idea(db, idea_id, estado=body.estado)
    except LookupError:
        return {"ok": False, "mensaje": "No encontré esa idea."}
    return {"ok": True, **rd.telegram_item(i)}


class MsgIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_id: int = Field(ge=1)


@router.post("/n8n/ideas/{idea_id}/message", dependencies=n8n)
async def n8n_idea_message(idea_id: int, body: MsgIn, db: AsyncSession = Depends(get_db)) -> dict:
    await rd.set_message_id(db, idea_id, body.message_id)
    return {"ok": True}


@router.get("/n8n/list", dependencies=n8n)
async def n8n_list(que: Literal["ideas", "backlog"] = "ideas", db: AsyncSession = Depends(get_db)) -> dict:
    if que == "backlog":
        items = await rd.ideas(db, estados=["backlog", "en_curso"])
        return {"mensaje": rd.list_message(items, "🗂 Backlog y en curso")}
    items = await rd.ideas(db, estados=["nueva", "me_interesa"])
    return {"mensaje": rd.list_message(items, "💡 Ideas nuevas y las que te interesan")}


@router.get("/n8n/help", dependencies=n8n)
async def n8n_help() -> dict:
    return {"mensaje": rd.HELP}


class IgnoredIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    chat_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    tipo: str = Field(default="", max_length=20)


@router.post("/n8n/ignored", dependencies=n8n)
async def n8n_ignored(body: IgnoredIn, db: AsyncSession = Depends(get_db)) -> dict:
    await rd.log_ignored(db, body.chat_hash, body.tipo)
    return {"ok": True}


# ---------------------------------------------------------------- consola v2+ (Admin V2)
@router.get("/admin/ideas", dependencies=admin)
async def admin_ideas(estado: str = Query(default="", max_length=14), categoria: str = Query(default="", max_length=40),
                      db: AsyncSession = Depends(get_db)) -> dict:
    return {"ideas": await rd.ideas(db, estado=estado, categoria=categoria), "counts": await rd.counts(db),
            "states": [{"key": k, "label": v} for k, v in rd.STATE_LABEL.items()],
            "categories": [{"key": k, "label": v} for k, v in rd.CATEGORY_LABEL.items()]}


class IdeaPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    estado: Optional[State] = None
    notas: Optional[str] = Field(default=None, max_length=2000)


@router.patch("/admin/ideas/{idea_id}", dependencies=admin)
async def admin_idea_patch(idea_id: int, body: IdeaPatch, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        i = await rd.update_idea(db, idea_id, estado=body.estado, notas=body.notas)
    except LookupError:
        raise HTTPException(status_code=404, detail="no_existe") from None
    if body.estado is not None and i.get("tg_message_id"):
        await _hook("nexus-editar", rd.telegram_item(i))   # el mensaje de NEXUS muestra el estado nuevo
    return {"ok": True, "idea": i}


@router.get("/admin/informes", dependencies=admin)
async def admin_informes(db: AsyncSession = Depends(get_db)) -> dict:
    inf = await rd.informes(db)
    return {"informes": inf, "a_pedido_hoy": await rd.on_demand_today(db), "tope_diario": rd.DAILY_ON_DEMAND,
            "costo_total_usd": round(sum(float(i["costo_usd"] or 0) for i in inf), 4)}


class TemaIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nombre: str = Field(min_length=3, max_length=120)
    descripcion: str = Field(default="", max_length=600)
    activo: bool = True


@router.get("/admin/temas", dependencies=admin)
async def admin_temas(db: AsyncSession = Depends(get_db)) -> dict:
    return {"temas": await rd.temas(db)}


@router.post("/admin/temas", dependencies=admin)
async def admin_tema_create(body: TemaIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"ok": True, "tema": await rd.save_tema(db, body.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.put("/admin/temas/{tema_id}", dependencies=admin)
async def admin_tema_update(tema_id: int, body: TemaIn, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"ok": True, "tema": await rd.save_tema(db, body.model_dump(), tema_id)}
    except LookupError:
        raise HTTPException(status_code=404, detail="no_existe") from None


# ---------------------------------------------------------------- consola -> n8n (generar ahora y reflejar en Telegram)
N8N_BASE_ENV = "NEXUS_N8N_BASE"
N8N_BASE_DEFAULT = "https://main-production-54df.up.railway.app"


async def _hook(path: str, payload: dict) -> bool:
    """Llama un webhook de n8n con el mismo token de servicio (X-Nexa-Token). Sin token o sin respuesta: False."""
    import os

    import httpx

    from app.api.v1.endpoints.prospecting import TOKEN_ENV
    token = os.getenv(TOKEN_ENV, "").strip()
    if not token:
        return False
    base = (os.getenv(N8N_BASE_ENV, "").strip() or N8N_BASE_DEFAULT).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{base}/webhook/{path}", json=payload, headers={"X-Nexa-Token": token})
        return r.status_code < 300
    except httpx.HTTPError:
        return False


class GenerateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tema: str = Field(default="", max_length=300)


@router.post("/admin/generar", dependencies=admin)
async def admin_generate(body: GenerateIn, db: AsyncSession = Depends(get_db)) -> dict:
    used = await rd.on_demand_today(db)
    if used >= rd.DAILY_ON_DEMAND:
        raise HTTPException(status_code=429, detail="tope_diario")
    if not await _hook("nexus-radar", {"tema": body.tema, "origen": "consola"}):
        raise HTTPException(status_code=502, detail="n8n_no_disponible")
    return {"ok": True, "usados": used + 1, "tope": rd.DAILY_ON_DEMAND}


@router.get("/n8n/informes/ultimo", dependencies=n8n)
async def n8n_last_report(db: AsyncSession = Depends(get_db)) -> dict:
    """Resumen del ultimo informe (operacion y verificacion): estado, costo, conteos y titulos de sus ideas."""
    inf = (await rd.informes(db, limit=1) or [None])[0]
    if not inf:
        return {"informe": None, "ideas": []}
    rows = await rd._rows(db, "SELECT id, titulo, puntaje, estado, fuentes FROM radar_ideas WHERE informe_id = :i ORDER BY puntaje DESC", {"i": inf["id"]})
    return {"informe": inf, "ideas": [{"id": r["id"], "titulo": r["titulo"], "puntaje": r["puntaje"], "estado": r["estado"],
                                        "fuente": ((r["fuentes"] or [{}])[0] or {}).get("url", "")} for r in rows]}
