"""Arqueo de caja a ciegas en el panel de caja (049M).

Antes vivia dentro del modulo Costos (049I); al desmontar Costos se conserva
aqui, con la misma tabla cash_counts (los arqueos historicos siguen igual) y
las mismas rutas relativas que ya usa el panel de caja.

Se activa por empresa con el ajuste "cash_count" del modulo de caja/mesero
(waiter_ordering); la migracion 022c lo enciende solo donde Costos estaba
activo (hoy ASADERO). Sin el ajuste, la caja cierra la jornada como siempre.
Todos los endpoints exigen sesion de la empresa (o Admin V2): el cajero hace
su arqueo; el dueño/administrador ve el historico y cuenta turnos pendientes.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_company_user_for_tenant
from app.services import cash_count as engine
from app.services.session_cutoff import load_policy, zone
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()
logger = logging.getLogger(__name__)
FLAG = "cash_count"
BASE_KEY = "cash_count_drawer_base"
SAVE_FAILED = "No se pudo registrar el arqueo. Puedes cerrar la jornada igual; queda anotado para el administrador."


def _clean(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _f(value: Any) -> float:
    return float(engine.money(value))


async def _caja_settings(db: AsyncSession, company_id: Any) -> dict | None:
    """Ajustes del modulo de caja/mesero si esta activo; None si no."""
    row = (await db.execute(text("""
        SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:company_id AS uuid) AND LOWER(m.code) = 'waiter_ordering' AND cm.enabled IS TRUE
        LIMIT 1
    """), {"company_id": str(company_id)})).mappings().first()
    if not row:
        return None
    raw = row.get("settings") or {}
    if isinstance(raw, str):
        raw = json.loads(raw or "{}")
    return raw if isinstance(raw, dict) else {}


async def cash_count_enabled(db: AsyncSession, company_id: Any) -> bool:
    try:
        settings = await _caja_settings(db, company_id)
    except Exception:
        return False
    return bool(settings and settings.get(FLAG) is True)


async def _actor(company_id: uuid.UUID, request: Request, authorization: str | None, db: AsyncSession) -> dict:
    if not await cash_count_enabled(db, company_id):
        raise HTTPException(status_code=403, detail="cash_count_not_enabled")
    if await active_admin_v2_session(request, db):
        return {"id": "", "name": "Admin V2", "kind": "owner"}
    user = await require_company_user_for_tenant(db, authorization, company_id)
    settings = getattr(user, "settings_json", None) or {}
    mini = settings.get("mini_panel") if isinstance(settings, dict) and isinstance(settings.get("mini_panel"), dict) else {}
    kind = engine.role_kind(getattr(user, "role", ""))
    if kind == "other" and str(mini.get("type") or "") == "caja":
        kind = "cashier"
    return {"id": str(user.id), "name": _clean(getattr(user, "full_name", "") or getattr(user, "email", "") or "Usuario", 180),
            "kind": kind}


async def require_cash_user(company_id: uuid.UUID, request: Request, authorization: str | None = Header(default=None),
                            db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _actor(company_id, request, authorization, db)
    if actor["kind"] == "other":
        raise HTTPException(status_code=403, detail="role_not_allowed")
    return actor


async def require_cash_manager(company_id: uuid.UUID, request: Request, authorization: str | None = Header(default=None),
                               db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _actor(company_id, request, authorization, db)
    if actor["kind"] not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Solo el dueño o el administrador.")
    return actor


async def open_cashier_session(db: AsyncSession, company_id: uuid.UUID, user_id: str | None = None) -> dict | None:
    """Turno de caja abierto (del cajero, o el ultimo abierto de la empresa)."""
    params = {"company_id": str(company_id)}
    where = ""
    if user_id:
        where = "AND user_id = CAST(:user_id AS uuid)"
        params["user_id"] = user_id
    row = (await db.execute(text(f"""
        SELECT id, user_id, started_at, ended_at, status FROM mini_panel_work_sessions
        WHERE company_id = CAST(:company_id AS uuid) AND panel_type = 'caja' AND status IN ('active', 'break') {where}
        ORDER BY started_at DESC LIMIT 1
    """), params)).mappings().first()
    return dict(row) if row else None


async def _legacy_drawer(db: AsyncSession, company_id: uuid.UUID, session_id: str) -> dict:
    """Gastos y retiros pagados del cajon que se registraron con Costos (ya
    desmontado): siguen contando para los turnos de entonces."""
    exists = (await db.execute(text("SELECT to_regclass('public.expenses') IS NOT NULL AS exists"))).mappings().first()
    if not exists or not exists.get("exists"):
        return {"expenses": 0, "withdrawals": 0}
    row = (await db.execute(text("""
        SELECT COALESCE(SUM(total) FILTER (WHERE category <> 'retiro_dueno'), 0) AS expenses,
               COALESCE(SUM(total) FILTER (WHERE category = 'retiro_dueno'), 0) AS withdrawals
        FROM expenses WHERE company_id = CAST(:c AS uuid) AND cashier_session_id = CAST(:sid AS uuid)
          AND paid_from = 'cajon' AND status <> 'rechazado'
    """), {"c": str(company_id), "sid": session_id})).mappings().first()
    return dict(row or {"expenses": 0, "withdrawals": 0})


async def expected_for_session(db: AsyncSession, company_id: uuid.UUID, session: dict, settings: dict) -> dict:
    """Lo que deberia haber en el cajon al cerrar ESTE turno de caja."""
    start = session["started_at"]
    end = session.get("ended_at") or datetime.now(timezone.utc)
    user_id = str(session.get("user_id") or "")
    sales = (await db.execute(text("""
        SELECT COALESCE(SUM(total), 0) AS total FROM hospitality_orders
        WHERE company_id = CAST(:c AS uuid) AND status = 'cerrado' AND payment_method = 'cash'
          AND closed_at >= :s AND closed_at <= :e
          AND (
                metadata->'closed_by'->>'id' = :u
             OR (metadata->'closed_by' IS NULL AND metadata->'cashier_sale'->'by'->>'id' = :u)
             OR (metadata->'closed_by' IS NULL AND metadata->'cashier_sale' IS NULL)
          )
    """), {"c": str(company_id), "s": start, "e": end, "u": user_id})).mappings().first()
    spent = await _legacy_drawer(db, company_id, str(session["id"]))
    base = engine.dec(settings.get(BASE_KEY) or 0)
    return {"base": base, "cash_sales": engine.money((sales or {}).get("total")),
            "drawer_expenses": engine.money(spent.get("expenses")), "withdrawals": engine.money(spent.get("withdrawals")),
            "expected": engine.expected_cash(base, (sales or {}).get("total"), spent.get("expenses"), spent.get("withdrawals")),
            "shift_start": start, "shift_end": session.get("ended_at")}


def _count_payload(row: dict, reveal: bool = True) -> dict:
    data = {"id": str(row["id"]), "cashier_name": row["cashier_name"], "counted": _f(row["counted"]), "status": row["status"],
            "observation": row.get("observation") or "", "blind": bool(row.get("blind")),
            "performed_by_name": row.get("performed_by_name") or "", "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "shift_start": row["shift_start"].isoformat() if row.get("shift_start") else None,
            "shift_end": row["shift_end"].isoformat() if row.get("shift_end") else None}
    if reveal:
        data.update({"base": _f(row["base"]), "cash_sales": _f(row["cash_sales"]), "drawer_expenses": _f(row["drawer_expenses"]),
                     "withdrawals": _f(row["withdrawals"]), "expected": _f(row["expected"]), "difference": _f(row["difference"]),
                     "result": engine.difference_label(row["difference"])})
    return data


async def _session_count(db: AsyncSession, company_id: uuid.UUID, session_id: str) -> dict | None:
    row = (await db.execute(text("SELECT * FROM cash_counts WHERE company_id = CAST(:c AS uuid) AND cashier_session_id = CAST(:s AS uuid)"),
                            {"c": str(company_id), "s": session_id})).mappings().first()
    return dict(row) if row else None


async def _insert_count(db: AsyncSession, company_id: uuid.UUID, session: dict, counted: Decimal, denominations: dict,
                        observation: str, actor: dict, blind: bool) -> dict:
    settings = await _caja_settings(db, company_id) or {}
    exp = await expected_for_session(db, company_id, session, settings)
    difference = engine.money(counted - exp["expected"])
    status_value = "cerrado" if difference == 0 or observation else "pendiente_observacion"
    cashier = (await db.execute(text("SELECT full_name FROM company_users WHERE id = CAST(:u AS uuid) AND company_id = CAST(:c AS uuid)"),
                                {"u": str(session.get("user_id") or uuid.UUID(int=0)), "c": str(company_id)})).mappings().first()
    count_id = str(uuid.uuid4())
    # 049Y: cada parametro aparece una sola vez. Antes :status se usaba en el
    # VALUES (varchar) y en un CASE (text): Postgres rechazaba el INSERT
    # ("inconsistent types deduced for parameter") y el except lo mostraba
    # como "ya tiene su arqueo", dejando al cajero sin poder cerrar.
    try:
        await db.execute(text("""
            INSERT INTO cash_counts (id, company_id, cashier_session_id, cashier_user_id, cashier_name, shift_start, shift_end,
                                     base, cash_sales, drawer_expenses, withdrawals, expected, counted, difference, denominations,
                                     observation, status, blind, performed_by_name, performed_by_kind, closed_at)
            VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(:sid AS uuid), :uid, :cname, :ss, :se,
                    :base, :sales, :exp, :wd, :expected, :counted, :diff, CAST(:den AS jsonb), :obs, :status, :blind, :by, :kind,
                    :closed_at)
        """), {"id": count_id, "c": str(company_id), "sid": str(session["id"]),
               "uid": str(session.get("user_id") or ""), "cname": (cashier or {}).get("full_name") or actor["name"],
               "ss": exp["shift_start"], "se": exp["shift_end"], "base": exp["base"], "sales": exp["cash_sales"],
               "exp": exp["drawer_expenses"], "wd": exp["withdrawals"], "expected": exp["expected"], "counted": counted,
               "diff": difference, "den": json.dumps(denominations or {}), "obs": _clean(observation, 1000), "status": status_value,
               "blind": blind, "by": actor["name"], "kind": actor["kind"],
               "closed_at": datetime.now(timezone.utc) if status_value == "cerrado" else None})
    except IntegrityError:
        # Ya habia un arqueo para este turno (doble toque, dos pestañas): se
        # devuelve el registrado; el conteo nunca se reemplaza.
        await db.rollback()
        existing = await _session_count(db, company_id, str(session["id"]))
        if existing:
            return {**existing, "already_registered": True}
        logger.exception("cash_count insert integrity error company=%s session=%s", company_id, session.get("id"))
        raise HTTPException(status_code=500, detail=SAVE_FAILED)
    except Exception:
        await db.rollback()
        logger.exception("cash_count insert failed company=%s session=%s", company_id, session.get("id"))
        raise HTTPException(status_code=500, detail=SAVE_FAILED)
    await db.commit()
    row = (await db.execute(text("SELECT * FROM cash_counts WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)"),
                            {"id": count_id, "c": str(company_id)})).mappings().first()
    return dict(row)


class BlindCountIn(BaseModel):
    counted: float | None = Field(default=None, ge=0)
    denominations: dict[str, int] | None = None


@router.get("/companies/{company_id}/caja/config")
async def cashier_config(company_id: uuid.UUID, actor: dict = Depends(require_cash_user)) -> dict:
    # Nunca incluye lo esperado: el arqueo del cajero es a ciegas.
    return {"enabled": True, "denominations": engine.DENOMINATIONS, "kind": actor["kind"]}


@router.get("/companies/{company_id}/caja/arqueo")
async def my_current_count(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), actor: dict = Depends(require_cash_user)) -> dict:
    """Arqueo ya registrado del turno abierto del cajero (para retomarlo si
    se recargo el panel). Si aun no conto, no devuelve nada esperado."""
    session = await open_cashier_session(db, company_id, actor["id"] or None)
    if not session:
        return {"count": None}
    row = await _session_count(db, company_id, str(session["id"]))
    if not row:
        return {"count": None}
    return {"count": {**_count_payload(row), "needs_observation": row["status"] == "pendiente_observacion"}}


@router.post("/companies/{company_id}/caja/arqueo")
async def blind_count(company_id: uuid.UUID, payload: BlindCountIn, db: AsyncSession = Depends(get_db),
                      actor: dict = Depends(require_cash_user)) -> dict:
    """El cajero digita lo que conto. Queda fijo; solo entonces se revela lo esperado.
    Si el turno ya tiene arqueo, devuelve ese (already_registered) en vez de
    fallar: el cajero sigue directo al cierre y el conteo no se cambia."""
    session = await open_cashier_session(db, company_id, actor["id"] or None)
    if not session:
        raise HTTPException(status_code=409, detail="No tienes un turno de caja abierto.")
    existing = await _session_count(db, company_id, str(session["id"]))
    if existing:
        return {**_count_payload(existing), "needs_observation": existing["status"] == "pendiente_observacion",
                "already_registered": True}
    try:
        from_denominations = engine.count_from_denominations({int(k): v for k, v in (payload.denominations or {}).items()})
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Revisa el conteo por billetes y monedas.") from exc
    counted = from_denominations if from_denominations is not None else (engine.money(payload.counted) if payload.counted is not None else None)
    if counted is None:
        raise HTTPException(status_code=400, detail="Digita cuánto efectivo contaste.")
    row = await _insert_count(db, company_id, session, counted, payload.denominations or {}, "", actor, blind=True)
    return {**_count_payload(row), "needs_observation": row["status"] == "pendiente_observacion",
            "already_registered": bool(row.get("already_registered"))}


class CloseIncidentIn(BaseModel):
    step: str = Field(default="", max_length=40)
    error: str = Field(default="", max_length=1000)
    counted: float | None = Field(default=None, ge=0)


@router.post("/companies/{company_id}/caja/cierre/incidencia")
async def close_incident(company_id: uuid.UUID, payload: CloseIncidentIn, db: AsyncSession = Depends(get_db),
                         actor: dict = Depends(require_cash_user)) -> dict:
    """049Y: algo fallo al cerrar la jornada (arqueo, observacion, Z). El
    cierre sigue igual; aqui queda el registro de lo que paso para el dueño
    (sale en los turnos pendientes de arqueo). Nunca bloquea el cierre."""
    session = await open_cashier_session(db, company_id, actor["id"] or None)
    try:
        await db.execute(text("""
            INSERT INTO cash_close_incidents (id, company_id, cashier_session_id, cashier_user_id, cashier_name, step, error, counted)
            VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(:sid AS uuid), :uid, :name, :step, :error, :counted)
        """), {"id": str(uuid.uuid4()), "c": str(company_id), "sid": str(session["id"]) if session else None,
               "uid": actor["id"], "name": actor["name"], "step": _clean(payload.step, 40), "error": _clean(payload.error, 1000),
               "counted": engine.money(payload.counted) if payload.counted is not None else None})
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("cash close incident not stored company=%s step=%s error=%s", company_id, payload.step, payload.error)
        return {"ok": True, "recorded": False}
    return {"ok": True, "recorded": True}


class ObservationIn(BaseModel):
    observation: str = Field(..., min_length=1, max_length=1000)


@router.post("/companies/{company_id}/caja/arqueo/{count_id}/observation")
async def count_observation(company_id: uuid.UUID, count_id: uuid.UUID, payload: ObservationIn, db: AsyncSession = Depends(get_db),
                            actor: dict = Depends(require_cash_user)) -> dict:
    row = (await db.execute(text("SELECT * FROM cash_counts WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)"),
                            {"id": str(count_id), "c": str(company_id)})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Arqueo no encontrado.")
    if actor["kind"] == "cashier" and row["cashier_user_id"] != actor["id"]:
        raise HTTPException(status_code=403, detail="Ese arqueo no es tuyo.")
    if row["status"] != "pendiente_observacion":
        raise HTTPException(status_code=409, detail="Ese arqueo ya está cerrado.")
    if not _clean(payload.observation):
        raise HTTPException(status_code=400, detail="La observación es obligatoria cuando hay diferencia.")
    await db.execute(text("""
        UPDATE cash_counts SET observation = :o, status = 'cerrado', closed_at = now()
        WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid) AND status = 'pendiente_observacion'
    """), {"o": _clean(payload.observation, 1000), "id": str(count_id), "c": str(company_id)})
    await db.commit()
    row = (await db.execute(text("SELECT * FROM cash_counts WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)"),
                            {"id": str(count_id), "c": str(company_id)})).mappings().first()
    return _count_payload(dict(row))


async def _today(db: AsyncSession, company_id: uuid.UUID) -> date:
    policy = await load_policy(db, company_id)
    return datetime.now(timezone.utc).astimezone(zone(policy["timezone"])).date()


@router.get("/companies/{company_id}/arqueos")
async def list_counts(company_id: uuid.UUID, start: date | None = None, end: date | None = None,
                      db: AsyncSession = Depends(get_db), _a: dict = Depends(require_cash_manager)) -> dict:
    today = await _today(db, company_id)
    start = start or today - timedelta(days=30)
    end = end or today
    rows = [dict(r) for r in (await db.execute(text("""
        SELECT * FROM cash_counts WHERE company_id = CAST(:c AS uuid) AND created_at::date BETWEEN :s AND :e ORDER BY created_at DESC
    """), {"c": str(company_id), "s": start, "e": end})).mappings().all()]
    by_cashier: dict[str, dict] = {}
    for r in rows:
        row = by_cashier.setdefault(r["cashier_name"], {"cashier_name": r["cashier_name"], "counts": 0, "shortage": Decimal("0"), "surplus": Decimal("0")})
        row["counts"] += 1
        diff = engine.dec(r["difference"])
        if diff < 0:
            row["shortage"] += -diff
        elif diff > 0:
            row["surplus"] += diff
    return {"counts": [_count_payload(r) for r in rows],
            "by_cashier": [{**v, "shortage": _f(v["shortage"]), "surplus": _f(v["surplus"])} for v in
                           sorted(by_cashier.values(), key=lambda v: -v["shortage"])]}


@router.get("/companies/{company_id}/arqueos/pending")
async def pending_counts(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _a: dict = Depends(require_cash_manager)) -> dict:
    """Turnos de caja cerrados sin arqueo (p. ej. los cerro el corte diario).
    Aqui SI se ve lo esperado: el dueño revisa, no cuenta su propio turno."""
    settings = await _caja_settings(db, company_id) or {}
    rows = [dict(r) for r in (await db.execute(text("""
        SELECT s.id, s.user_id, s.started_at, s.ended_at, s.status, s.closed_reason, u.full_name
        FROM mini_panel_work_sessions s LEFT JOIN company_users u ON u.id = s.user_id
        WHERE s.company_id = CAST(:c AS uuid) AND s.panel_type = 'caja' AND s.status = 'finished'
          AND s.started_at >= now() - interval '45 days'
          AND NOT EXISTS (SELECT 1 FROM cash_counts k WHERE k.company_id = s.company_id AND k.cashier_session_id = s.id)
        ORDER BY s.started_at DESC
    """), {"c": str(company_id)})).mappings().all()]
    incidents = await _incidents_by_session(db, company_id, [str(s["id"]) for s in rows])
    out = []
    for s in rows:
        exp = await expected_for_session(db, company_id, s, settings)
        out.append({"session_id": str(s["id"]), "cashier_name": s.get("full_name") or "Cajero",
                    "shift_start": s["started_at"].isoformat(), "shift_end": s["ended_at"].isoformat() if s.get("ended_at") else None,
                    "closed_reason": s.get("closed_reason") or "", "base": _f(exp["base"]), "cash_sales": _f(exp["cash_sales"]),
                    "drawer_expenses": _f(exp["drawer_expenses"]), "withdrawals": _f(exp["withdrawals"]), "expected": _f(exp["expected"]),
                    "incidents": incidents.get(str(s["id"]), [])})
    return {"pending": out}


async def _incidents_by_session(db: AsyncSession, company_id: uuid.UUID, session_ids: list[str]) -> dict[str, list]:
    """Lo que fallo al cerrar cada turno (049Y). Sin la tabla, nada."""
    if not session_ids:
        return {}
    try:
        rows = (await db.execute(text("""
            SELECT cashier_session_id, step, error, counted, created_at FROM cash_close_incidents
            WHERE company_id = CAST(:c AS uuid) AND cashier_session_id = ANY(CAST(:ids AS uuid[]))
            ORDER BY created_at
        """), {"c": str(company_id), "ids": session_ids})).mappings().all()
    except Exception:
        await db.rollback()
        return {}
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(str(r["cashier_session_id"]), []).append(
            {"step": r["step"], "error": r["error"], "counted": _f(r["counted"]) if r.get("counted") is not None else None,
             "created_at": r["created_at"].isoformat() if r.get("created_at") else None})
    return out


class AdminCountIn(BaseModel):
    session_id: str
    counted: float = Field(..., ge=0)
    observation: str = Field(default="", max_length=1000)


@router.post("/companies/{company_id}/arqueos/admin")
async def admin_count(company_id: uuid.UUID, payload: AdminCountIn, db: AsyncSession = Depends(get_db),
                      actor: dict = Depends(require_cash_manager)) -> dict:
    try:
        sid = str(uuid.UUID(payload.session_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Turno no encontrado.")
    session = (await db.execute(text("""
        SELECT id, user_id, started_at, ended_at, status FROM mini_panel_work_sessions
        WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid) AND panel_type = 'caja' AND status = 'finished'
    """), {"id": sid, "c": str(company_id)})).mappings().first()
    if not session:
        raise HTTPException(status_code=404, detail="Turno de caja no encontrado o aún abierto.")
    settings = await _caja_settings(db, company_id) or {}
    exp = await expected_for_session(db, company_id, dict(session), settings)
    if engine.money(Decimal(str(payload.counted)) - exp["expected"]) != 0 and not _clean(payload.observation):
        raise HTTPException(status_code=400, detail="Hay diferencia: la observación es obligatoria.")
    row = await _insert_count(db, company_id, dict(session), engine.money(payload.counted), {}, payload.observation, actor, blind=False)
    return _count_payload(row)
