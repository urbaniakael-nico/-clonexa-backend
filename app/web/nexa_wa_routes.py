"""Consola v2+ · Conversaciones Nexa (solo Admin V2, 401 sin sesion).

- GET  /admin-v2/api/nexa-wa/conversations: lista con filtros (etapa, fechas,
  buscador), conteo por etapa y "nuevas" (con mensajes que aun no se abrieron).
- GET  /admin-v2/api/nexa-wa/conversations/{id}: conversacion completa (solo
  lectura), datos detectados y estado de entregas. Abrirla la marca como vista.
- POST .../{id}/pause {paused}: Pausar / Reanudar Nexa.
- POST .../{id}/not-interested: etapa no_interesado.
- GET  .../{id}/export.csv: la conversacion en CSV.
Las conversaciones son de la propia Clonexa (sin company_id) y las guarda
app/services/nexa_whatsapp.py.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import nexa_whatsapp as nw
from app.web import admin_v2_routes as v2
from app.web.admin_v2plus_companies import GUARD, _audit, _json

router = APIRouter()
API = "/admin-v2/api/nexa-wa"


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if value else None


def _cid(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        raise HTTPException(status_code=404, detail="Conversación no encontrada.") from None


def _day(value: str, name: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} debe ser AAAA-MM-DD") from None


def _row(c: dict) -> dict:
    seen = c.get("admin_seen_at")
    unread = bool(c.get("last_inbound_at") and (not seen or c["last_inbound_at"] > seen))
    return {"id": c["id"], "wa_id": c["wa_id"], "nombre": c.get("profile_name"), "tipo_negocio": c.get("business_type"),
            "ciudad": c.get("city"), "etapa": c["stage"], "nexa_pausada": bool(c.get("nexa_paused")), "ultimo": c.get("last_preview"),
            "ultimo_at": _iso(c.get("last_message_at")), "nueva": unread}


@router.get(f"{API}/conversations", include_in_schema=False, dependencies=GUARD)
async def conversations(stage: str = "", q: str = "", desde: str = "", hasta: str = "", db: AsyncSession = Depends(get_db)):
    if stage and stage not in nw.STAGES:
        raise HTTPException(status_code=422, detail="Etapa no válida.")
    start, end = _day(desde, "desde"), _day(hasta, "hasta")
    where, p = ["TRUE"], {}
    if start:
        where.append("last_message_at >= :start")
        p["start"] = datetime(start.year, start.month, start.day, tzinfo=nw.BOGOTA)
    if end:
        where.append("last_message_at < :end")
        p["end"] = datetime(end.year, end.month, end.day, tzinfo=nw.BOGOTA) + timedelta(days=1)
    term = q.strip()[:80]
    if term:
        where.append("(profile_name ILIKE :q OR wa_id LIKE :qd OR business_type ILIKE :q OR city ILIKE :q OR email ILIKE :q)")
        like = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        p["q"] = f"%{like}%"
        p["qd"] = f"%{''.join(ch for ch in term if ch.isdigit()) or like}%"
    base = " AND ".join(where)
    counts = {r["stage"]: int(r["n"]) for r in (await db.execute(text(
        f"SELECT stage, COUNT(*) AS n FROM wa_contacts WHERE {base} GROUP BY stage"), p)).mappings().all()}
    if stage:
        where.append("stage = :stage")
        p["stage"] = stage
    rows = (await db.execute(text(f"""
        SELECT {nw.CONTACT_COLS} FROM wa_contacts WHERE {' AND '.join(where)}
        ORDER BY last_message_at DESC NULLS LAST, created_at DESC LIMIT 500
    """), p)).mappings().all()
    nuevas = int((await db.execute(text(
        "SELECT COUNT(*) FROM wa_contacts WHERE last_inbound_at IS NOT NULL AND (admin_seen_at IS NULL OR last_inbound_at > admin_seen_at)"
    ))).scalar() or 0)
    return _json({"ok": True, "items": [_row(dict(r)) for r in rows], "counts": {s: counts.get(s, 0) for s in nw.STAGES},
                  "total": sum(counts.values()), "nuevas": nuevas, "now": _iso(nw.now())})


async def _load(db: AsyncSession, contact_id: str) -> dict:
    contact = await nw.contact_by_id(db, _cid(contact_id))
    if not contact:
        raise HTTPException(status_code=404, detail="Conversación no encontrada.")
    return contact


async def _messages(db: AsyncSession, contact_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT * FROM (
            SELECT id::text AS id, meta_id, direction, msg_type, body, reply_id, options, status, error, created_at, status_at
            FROM wa_messages WHERE contact_id = CAST(:id AS uuid) ORDER BY created_at DESC, id DESC LIMIT 1000
        ) m ORDER BY created_at, id
    """), {"id": contact_id})).mappings().all()
    return [{"id": r["id"], "direccion": r["direction"], "tipo": r["msg_type"], "texto": r["body"], "opciones": r["options"] or [],
             "estado": r["status"], "error": r["error"], "creado": _iso(r["created_at"]), "estado_at": _iso(r["status_at"])} for r in rows]


def _detail(contact: dict, messages: list[dict]) -> dict:
    out = [m for m in messages if m["direccion"] == "out"]
    deliveries = {k: sum(1 for m in out if m["estado"] == k) for k in ("sent", "delivered", "read", "failed")}
    return {"ok": True, "contacto": {**nw.contact_public(contact), "notas": contact.get("notes"), "etapa_at": _iso(contact.get("stage_at"))},
            "mensajes": [m for m in messages if m["tipo"] != "pendiente" or m["texto"]], "entregas": deliveries}


@router.get(f"{API}/conversations/{{contact_id}}", include_in_schema=False, dependencies=GUARD)
async def conversation(contact_id: str, db: AsyncSession = Depends(get_db)):
    contact = await _load(db, contact_id)
    await db.execute(text("UPDATE wa_contacts SET admin_seen_at = now() WHERE id = CAST(:id AS uuid)"), {"id": contact["id"]})
    await db.commit()
    return _json(_detail(contact, await _messages(db, contact["id"])))


class PauseIn(BaseModel):
    paused: bool


@router.post(f"{API}/conversations/{{contact_id}}/pause", include_in_schema=False, dependencies=GUARD)
async def pause(contact_id: str, body: PauseIn, request: Request, db: AsyncSession = Depends(get_db)):
    contact = await _load(db, contact_id)
    await db.execute(text("UPDATE wa_contacts SET nexa_paused = :p, updated_at = now() WHERE id = CAST(:id AS uuid)"),
                     {"p": body.paused, "id": contact["id"]})
    await db.commit()
    await _audit(request, nexa_wa="pausar" if body.paused else "reanudar", numero=contact["wa_id"])
    contact = await _load(db, contact["id"])
    return _json(_detail(contact, await _messages(db, contact["id"])))


@router.post(f"{API}/conversations/{{contact_id}}/not-interested", include_in_schema=False, dependencies=GUARD)
async def not_interested(contact_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    contact = await _load(db, contact_id)
    if contact["stage"] != "baja":
        await nw.set_stage(db, contact["id"], "no_interesado")
        await db.commit()
    await _audit(request, nexa_wa="no interesado", numero=contact["wa_id"])
    contact = await _load(db, contact["id"])
    return _json(_detail(contact, await _messages(db, contact["id"])))


def _cell(value: Any) -> str:
    """Sin formulas al abrir el CSV en Excel/Sheets."""
    value = "" if value is None else str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@router.get(f"{API}/conversations/{{contact_id}}/export.csv", include_in_schema=False, dependencies=GUARD)
async def export_csv(contact_id: str, db: AsyncSession = Depends(get_db)):
    contact = await _load(db, contact_id)
    messages = await _messages(db, contact["id"])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["numero", "nombre", "negocio", "ciudad", "tamano", "dolor", "correo", "etapa"])
    w.writerow([_cell(v) for v in (contact["wa_id"], contact.get("profile_name"), contact.get("business_type"), contact.get("city"),
                                   contact.get("size"), contact.get("main_pain"), contact.get("email"), contact["stage"])])
    w.writerow([])
    w.writerow(["fecha", "quien", "tipo", "texto", "opciones", "estado"])
    for m in messages:
        if m["tipo"] == "pendiente" and not m["texto"]:
            continue
        w.writerow([_cell(v) for v in (m["creado"], "cliente" if m["direccion"] == "in" else "Nexa", m["tipo"], m["texto"],
                                       " | ".join(str(o) for o in m["opciones"]) if isinstance(m["opciones"], list) else "", m["estado"])])
    data = "﻿" + buf.getvalue()
    return v2._no_store(Response(data, media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="nexa-{contact["wa_id"]}.csv"'}))
