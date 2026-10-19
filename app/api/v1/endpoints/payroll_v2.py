"""Nomina v2 (interruptor payroll_v2): detalle por turno y vista previa de
"confirmar salida". NO cambia el calculo: lee lo que ya existe.

- GET  /payroll/companies/{id}/period-activity    lo que hizo cada persona en el
  periodo, segun los modulos de la empresa: GPS (ubicacion y perimetro),
  Referencias (sesiones y cierres de produccion) y mini paneles (seccion,
  conexion/salida y, en restaurante, pedidos tomados, listos en cocina y
  cobros). Una consulta por tipo para TODO el periodo (no una por turno), todas
  filtradas por company_id. El portal cruza cada dato con su turno por hora.
- POST /payroll/companies/{id}/closures/preview  como quedaria la nomina de esa
  persona si se confirma la hora real propuesta: recalcula el periodo con ese
  unico turno tratado como confirmado (contextvar, sin escribir nada) y
  devuelve antes y despues. Confirmar sigue siendo el endpoint de siempre.

Ambas exigen sesion: Admin V2 o usuario de ESA empresa (y en restaurante, no
el rol "administrador", igual que Nomina).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints import payroll as core
from app.api.v1.endpoints import workforce_sessions as sessions_ep

router = APIRouter()
GPS_LIMIT = 5000
ORDER_LIMIT = 20000


def _iso(value: Any) -> str | None:
    dt = core._cx_payroll_dt_023o(value)
    return dt.isoformat() if dt else None


def _json(value: Any) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value or "{}")
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _modules(db: AsyncSession, company_id: UUID) -> set[str]:
    result = await db.execute(text("""
        SELECT LOWER(m.code) AS code FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:company_id AS uuid) AND cm.enabled IS TRUE
    """), {"company_id": str(company_id)})
    return {str(r["code"]) for r in result.mappings().all()}


SHIFT_LIST_FLAG = "payroll_shift_list"


async def shift_list_on(db: AsyncSession, company_id: UUID) -> bool:
    """Interruptor payroll_shift_list (modulo payroll): desglose de turnos en lista. Solo presentacion."""
    row = (await db.execute(text("""
        SELECT cm.enabled, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:company_id AS uuid) AND LOWER(m.code) = 'payroll' LIMIT 1
    """), {"company_id": str(company_id)})).mappings().first()
    settings = row["settings"] if row else None
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except ValueError:
            settings = {}
    return bool(row and row["enabled"] and isinstance(settings, dict) and settings.get(SHIFT_LIST_FLAG) is True)


def _bounds(period_start: date, period_end: date) -> tuple[datetime, datetime]:
    start_dt, end_dt = core.period_datetime_bounds(period_start, period_end)
    # Mismo margen que el calculo: turnos que empiezan antes o terminan despues del corte.
    return start_dt - timedelta(days=2), end_dt + core.SHIFT_LOOKAHEAD_049L


def _dates(period_start: date | None, period_end: date | None) -> tuple[date, date]:
    if not period_start or not period_end:
        raise HTTPException(status_code=400, detail="Faltan las fechas del periodo.")
    if period_end < period_start:
        raise HTTPException(status_code=400, detail="period_end_before_start")
    if (period_end - period_start).days > 62:
        raise HTTPException(status_code=400, detail="El periodo no puede pasar de 62 días.")
    return period_start, period_end


# ------------------------------------------------------------ actividad
async def period_activity(db: AsyncSession, company_id: UUID, period_start: date, period_end: date) -> dict:
    cid = str(company_id)
    lo, hi = _bounds(period_start, period_end)
    modules = await _modules(db, company_id)
    out: dict[str, Any] = {"modules": {"gps": "gps" in modules, "references": "references" in modules, "panels": False, "orders": False},
                           "documents": {}, "gps": {}, "references": {}, "reference_closures": {}, "panels": {}}
    if await shift_list_on(db, company_id):
        out["ui"] = {"shift_list": True}  # sin el interruptor la respuesta queda igual

    docs = await db.execute(text("""
        SELECT id::text AS id, COALESCE(document_id, '') AS document_id
        FROM employees WHERE company_id = CAST(:company_id AS uuid)
    """), {"company_id": cid})
    out["documents"] = {r["id"]: r["document_id"] for r in docs.mappings().all() if r["document_id"]}

    if out["modules"]["gps"]:
        rows = await db.execute(text("""
            SELECT employee_id::text AS employee_id, COALESCE(occurred_at, created_at) AS at, payload_json, detail
            FROM workforce_attendance_events
            WHERE company_id = CAST(:company_id AS uuid) AND event_type = 'gps_location'
              AND COALESCE(occurred_at, created_at) >= :lo AND COALESCE(occurred_at, created_at) <= :hi
            ORDER BY COALESCE(occurred_at, created_at) ASC
            LIMIT :limit
        """), {"company_id": cid, "lo": lo, "hi": hi, "limit": GPS_LIMIT})
        for r in rows.mappings().all():
            p = _json(r["payload_json"])
            lat, lng = p.get("latitude"), p.get("longitude")
            if (lat is None or lng is None) and r.get("detail") and "," in str(r["detail"]):
                lat, lng = (part.strip() for part in str(r["detail"]).split(",", 1))
            out["gps"].setdefault(r["employee_id"] or "", []).append({
                "at": _iso(r["at"]), "lat": _num(lat), "lng": _num(lng),
                "perimeter": str(p.get("matched_perimeter_name") or ""), "status": str(p.get("gps_status_label") or p.get("gps_status") or ""),
            })

    if out["modules"]["references"] and await core._cx_payroll_table_exists_023o(db, "reference_work_sessions"):
        rows = await db.execute(text("""
            SELECT employee_id, COALESCE(reference_name, '') AS reference_name, started_at, ended_at, duration_minutes, COALESCE(status, '') AS status
            FROM reference_work_sessions
            WHERE company_id = :company_id AND started_at <= :hi AND COALESCE(ended_at, now()) >= :lo
            ORDER BY started_at ASC
        """), {"company_id": cid, "lo": lo, "hi": hi})
        for r in rows.mappings().all():
            out["references"].setdefault(str(r["employee_id"] or ""), []).append({
                "reference": r["reference_name"], "start": _iso(r["started_at"]), "end": _iso(r["ended_at"]),
                "minutes": round(_num(r["duration_minutes"])), "status": r["status"],
            })
        if await core._cx_payroll_table_exists_023o(db, "reference_production_closures"):
            rows = await db.execute(text("""
                SELECT employee_id, COALESCE(reference_name, '') AS reference_name, COALESCE(size, '') AS size,
                       COALESCE(quantity_finished, 0) AS quantity, closed_at
                FROM reference_production_closures
                WHERE company_id = :company_id AND closed_at >= :lo AND closed_at <= :hi
                ORDER BY closed_at ASC
            """), {"company_id": cid, "lo": lo, "hi": hi})
            for r in rows.mappings().all():
                out["reference_closures"].setdefault(str(r["employee_id"] or ""), []).append({
                    "reference": r["reference_name"], "size": r["size"], "quantity": int(r["quantity"] or 0), "at": _iso(r["closed_at"]),
                })

    if await core._cx_payroll_table_exists_023o(db, "mini_panel_work_sessions"):
        rows = await db.execute(text("""
            SELECT id::text AS id, user_id::text AS user_id, employee_id::text AS employee_id, COALESCE(panel_type, '') AS panel_type,
                   started_at, ended_at, COALESCE(location_label, '') AS location_label
            FROM mini_panel_work_sessions
            WHERE company_id = CAST(:company_id AS uuid) AND started_at <= :hi AND COALESCE(ended_at, now()) >= :lo
        """), {"company_id": cid, "lo": lo, "hi": hi})
        sessions = [dict(r) for r in rows.mappings().all()]
        out["modules"]["panels"] = bool(sessions)
        for s in sessions:
            out["panels"][s["id"]] = {"panel_type": s["panel_type"], "start": _iso(s["started_at"]), "end": _iso(s["ended_at"]),
                                      "location": s["location_label"], "employee_id": s["employee_id"] or ""}
        restaurant = bool({"waiter_ordering", "hospitality"} & modules)
        if sessions and restaurant and await core._cx_payroll_table_exists_023o(db, "hospitality_orders"):
            out["modules"]["orders"] = True
            await _orders_by_session(db, cid, lo, hi, sessions, out["panels"])
    return out


async def _orders_by_session(db: AsyncSession, cid: str, lo: datetime, hi: datetime, sessions: list[dict], panels: dict) -> None:
    """Lo que el sistema guarda por persona en restaurante: mesero que tomo el
    pedido (metadata.waiter.id), quien lo dejo listo en cocina
    (metadata.kitchen.ready_by.id) y quien cobro (metadata.closed_by.id). Esos
    ids son la cuenta del mini panel (= user_id de la sesion de trabajo)."""
    rows = await db.execute(text("""
        SELECT created_at, COALESCE(total, 0) AS total, closed_at,
               metadata->'waiter'->>'id' AS waiter_id,
               metadata->'kitchen'->'ready_by'->>'id' AS ready_by, metadata->'kitchen'->>'ready_at' AS ready_at,
               metadata->'closed_by'->>'id' AS closed_by, metadata->'closed_by'->>'at' AS closed_by_at
        FROM hospitality_orders
        WHERE company_id = CAST(:company_id AS uuid)
          AND created_at >= :lo AND created_at <= :hi
          AND cancelled_at IS NULL AND COALESCE(status, '') NOT IN ('cancelled', 'cancelado', 'anulado')
        LIMIT :limit
    """), {"company_id": cid, "lo": lo - timedelta(days=1), "hi": hi, "limit": ORDER_LIMIT})
    orders = [dict(r) for r in rows.mappings().all()]
    now = datetime.now(timezone.utc)
    for s in sessions:
        user, start = s.get("user_id"), core._cx_payroll_dt_023o(s.get("started_at"))
        end = core._cx_payroll_dt_023o(s.get("ended_at")) or now
        if not user or not start:
            continue

        def inside(value: Any) -> bool:
            at = core._cx_payroll_dt_023o(value)
            return bool(at and start <= at <= end)

        taken = [o for o in orders if o["waiter_id"] == user and inside(o["created_at"])]
        ready = [o for o in orders if o["ready_by"] == user and inside(o["ready_at"])]
        charged = [o for o in orders if o["closed_by"] == user and inside(o["closed_by_at"] or o["closed_at"])]
        panels[s["id"]].update({
            "orders_taken": len(taken), "orders_taken_total": round(sum(_num(o["total"]) for o in taken), 2),
            "orders_ready": len(ready),
            "charges": len(charged), "charges_total": round(sum(_num(o["total"]) for o in charged), 2),
        })


@router.get("/companies/{company_id}/period-activity")
async def payroll_period_activity(
    company_id: UUID,
    period_start: date | None = Query(None), period_end: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _reader: str = Depends(core._require_period_reader_049L),
    _not_admin: None = Depends(core._NOT_ADMINISTRADOR),
) -> dict:
    start, end = _dates(period_start, period_end)
    await core.use_company_tz_052C(db, company_id)  # Fase A: limites del periodo en la zona de la empresa
    return await period_activity(db, company_id, start, end)


# ------------------------------------------------------- vista previa
def _person(snapshot: dict, employee_id: str) -> dict:
    row = next((r for r in snapshot.get("rows") or [] if str(r.get("employee_id")) == employee_id), None) or {}
    return {key: row.get(key, 0) for key in ("regular_minutes", "extra_minutes", "gross_amount", "discount_amount", "net_amount", "closed_shifts")}


@router.post("/companies/{company_id}/closures/preview")
async def payroll_closure_preview(
    company_id: UUID, payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    _reader: str = Depends(core._require_period_reader_049L),
    _not_admin: None = Depends(core._NOT_ADMINISTRADOR),
) -> dict:
    data = payload or {}
    try:
        start = date.fromisoformat(str(data.get("period_start") or ""))
        end = date.fromisoformat(str(data.get("period_end") or ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Fechas del periodo inválidas.") from None
    start, end = _dates(start, end)
    source, ref = str(data.get("source") or ""), str(data.get("session_ref") or "")
    if source not in {"attendance", "mini_panel"} or not ref:
        raise HTTPException(status_code=400, detail="Turno inválido.")

    before = await core.calculate_period_snapshot(db, company_id, start, end)
    item = next((u for u in before.get("unverified_shifts") or [] if u.get("source") == source and str(u.get("session_ref")) == ref), None)
    if not item:
        raise HTTPException(status_code=404, detail="Ese turno no está pendiente de confirmar en este periodo.")
    if item.get("status") == "confirmed":
        raise HTTPException(status_code=409, detail="La hora real ya fue registrada y no se puede cambiar.")
    tz = await sessions_ep._tz(db, company_id)
    real_end = sessions_ep._parse_end(data.get("real_end_at"), tz)
    sessions_ep._check_range({"started_at": item.get("start"), "system_end_at": item.get("end")}, real_end)

    token = core.PREVIEW_CLOSURES_052A.set({(source, ref): {"id": item.get("closure_id"), "source": source, "session_ref": ref,
                                                            "status": "confirmed", "reason": item.get("reason"), "real_end_at": real_end}})
    try:
        after = await core.calculate_period_snapshot(db, company_id, start, end)
    finally:
        core.PREVIEW_CLOSURES_052A.reset(token)
    employee_id = str(item.get("employee_id") or "")
    return {"employee_id": employee_id, "start": item.get("start"), "system_end": item.get("end"), "real_end": real_end.isoformat(),
            "before": _person(before, employee_id), "after": _person(after, employee_id),
            "legal_mode": (after.get("legal_mode") or {}).get("state") if isinstance(after.get("legal_mode"), dict) else None}
