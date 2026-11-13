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
    return await rd.start_report(db, tipo=body.tipo, tema=body.tema, origen=body.origen)


class FailIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    informe_id: int = Field(ge=1)
    error: str = Field(default="", max_length=500)


@router.post("/n8n/fail", dependencies=n8n)
async def n8n_fail(body: FailIn, db: AsyncSession = Depends(get_db)) -> dict:
    await rd.fail_report(db, body.informe_id, body.error)
    return {"ok": True, "mensaje": f"⚠️ NEXUS: el informe #{body.informe_id} falló ({rd.esc(body.error[:120]) or 'error'})."}


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
