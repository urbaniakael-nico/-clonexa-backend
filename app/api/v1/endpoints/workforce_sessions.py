"""Corte diario de sesiones (049D): aviso, hora real de salida y alertas en vivo.

Aplica a TODAS las empresas. El corte lo hace app/services/session_cutoff.py.

- El administrador o dueño (o Admin V2) registra la hora real de salida de
  un turno cerrado por el sistema: una sola vez, queda bloqueada (tambien en
  la base, por trigger) con quien y cuando.
- El empleado solo puede PROPONER su hora ("declarada por el empleado");
  no cuenta para el pago hasta que el administrador la confirme.
- Mientras no se confirme, esas horas no se liquidan (payroll.py).

Todos los endpoints exigen sesion valida de la empresa (o Admin V2) y toda
consulta filtra por company_id.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES, get_db, require_company_user_for_tenant
from app.services import session_cutoff as cutoff
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()

SESSION_ADMIN_ROLES = ADMIN_ROLES | {
    "manager", "gerencia", "gerente", "dueno", "dueño", "owner", "propietario", "administrador",
}


# ---------------------------------------------------------------- auth ---
async def require_session_admin(
    company_id: uuid.UUID, request: Request,
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> dict:
    """Administrador o dueño de ESTA empresa, o Admin V2."""
    if await active_admin_v2_session(request, db):
        return {"id": "", "name": "Admin V2"}
    user = await require_company_user_for_tenant(db, authorization, company_id, allowed_roles=SESSION_ADMIN_ROLES)
    return {"id": str(user.id), "name": str(getattr(user, "full_name", "") or getattr(user, "email", "") or "Administrador")}


async def require_session_user(
    company_id: uuid.UUID, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> dict:
    """Cualquier usuario de ESTA empresa; trae el empleado de Workforce vinculado."""
    user = await require_company_user_for_tenant(db, authorization, company_id)
    settings = getattr(user, "settings_json", None) or {}
    mini_panel = settings.get("mini_panel") if isinstance(settings, dict) and isinstance(settings.get("mini_panel"), dict) else {}
    return {
        "id": str(user.id),
        "name": str(getattr(user, "full_name", "") or getattr(user, "email", "") or "Empleado"),
        "employee_id": str(mini_panel.get("employee_id") or ""),
    }


# ------------------------------------------------------------- helpers ---
async def _tz(db: AsyncSession, company_id: uuid.UUID):
    return cutoff.zone((await cutoff.load_policy(db, company_id))["timezone"])


def _parse_end(value: Any, tz) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Hora de salida invalida.")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)  # lo que escribe la persona es hora local de la empresa
    return dt.astimezone(timezone.utc)


def _check_range(row: dict, end: datetime) -> None:
    started = cutoff.aware(row["started_at"])
    system_end = cutoff.aware(row["system_end_at"])
    if end <= started:
        raise HTTPException(status_code=400, detail="La hora de salida debe ser posterior a la entrada.")
    if end > system_end:
        raise HTTPException(status_code=400, detail="La hora de salida no puede ser posterior al cierre del sistema.")


async def _closure(db: AsyncSession, company_id: uuid.UUID, closure_id: Any) -> dict:
    try:
        clean_id = str(uuid.UUID(str(closure_id)))
    except ValueError:
        raise HTTPException(status_code=404, detail="Cierre no encontrado.")
    result = await db.execute(
        text("SELECT * FROM workforce_session_closures WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid)"),
        {"id": clean_id, "company_id": str(company_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Cierre no encontrado.")
    return dict(row)


async def _closure_by_ref(db: AsyncSession, company_id: uuid.UUID, source: str, ref: str) -> dict | None:
    result = await db.execute(
        text("""
            SELECT * FROM workforce_session_closures
            WHERE company_id = CAST(:company_id AS uuid) AND source = :source AND session_ref = :ref
        """),
        {"company_id": str(company_id), "source": source, "ref": ref},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _create_from_source(db: AsyncSession, company_id: uuid.UUID, source: str, ref: str) -> dict:
    """Turno sin fila de cierre (historico o cierre viejo): se crea con los
    datos reales del turno de ESTA empresa antes de registrar la hora."""
    cid = str(company_id)
    if source == "mini_panel":
        try:
            ref = str(uuid.UUID(ref))
        except ValueError:
            raise HTTPException(status_code=404, detail="Turno no encontrado.")
        result = await db.execute(
            text("""
                SELECT s.id, s.employee_id, s.panel_type, s.started_at, s.ended_at, s.closed_reason, e.full_name
                FROM mini_panel_work_sessions s
                LEFT JOIN employees e ON e.id = s.employee_id AND e.company_id = s.company_id
                WHERE s.id = CAST(:id AS uuid) AND s.company_id = CAST(:company_id AS uuid) AND s.status = 'finished'
            """),
            {"id": ref, "company_id": cid},
        )
        row = result.mappings().first()
        if not row or not row.get("ended_at"):
            raise HTTPException(status_code=404, detail="Turno no encontrado.")
        reason = row["closed_reason"] if row.get("closed_reason") in cutoff.SYSTEM_CLOSE_REASONS else cutoff.REASON_HISTORIC
        values = dict(employee_id=str(row.get("employee_id") or ""), employee_name=row.get("full_name") or "Colaborador",
                      panel_type=row.get("panel_type"), reason=reason, started_at=row["started_at"], system_end_at=row["ended_at"])
    elif source == "attendance":
        try:
            ref = str(uuid.UUID(ref))
        except ValueError:
            raise HTTPException(status_code=404, detail="Turno no encontrado.")
        result = await db.execute(
            text("""
                SELECT ev.employee_id, COALESCE(ev.occurred_at, ev.created_at) AS started_at, e.full_name,
                       (SELECT COALESCE(out.occurred_at, out.created_at)
                          FROM workforce_attendance_events out
                         WHERE out.company_id = ev.company_id AND out.employee_id = ev.employee_id
                           AND out.event_type IN ('check_out', 'salida', 'end_shift', 'shift_end')
                           AND COALESCE(out.occurred_at, out.created_at) > COALESCE(ev.occurred_at, ev.created_at)
                         ORDER BY COALESCE(out.occurred_at, out.created_at) ASC LIMIT 1) AS ended_at
                FROM workforce_attendance_events ev
                JOIN employees e ON e.id = ev.employee_id AND e.company_id = ev.company_id
                WHERE ev.id = CAST(:id AS uuid) AND ev.company_id = CAST(:company_id AS uuid)
            """),
            {"id": ref, "company_id": cid},
        )
        row = result.mappings().first()
        if not row or not row.get("ended_at"):
            raise HTTPException(status_code=404, detail="Turno no encontrado.")
        values = dict(employee_id=str(row["employee_id"]), employee_name=row.get("full_name") or "Colaborador",
                      panel_type="asistencia", reason=cutoff.REASON_HISTORIC, started_at=row["started_at"],
                      system_end_at=row["ended_at"])
    else:
        raise HTTPException(status_code=400, detail="source_invalid")
    await cutoff.insert_closure(db, company_id=cid, source=source, session_ref=ref, **values)
    created = await _closure_by_ref(db, company_id, source, ref)
    if not created:
        raise HTTPException(status_code=500, detail="No se pudo registrar el cierre.")
    return created


# ------------------------------------------------------------ lecturas ---
async def _live_alerts(db: AsyncSession, company_id: uuid.UUID, alert_hours: float, now: datetime) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT s.id, s.employee_id, s.panel_type, s.started_at, COALESCE(e.full_name, u.full_name) AS name
            FROM mini_panel_work_sessions s
            LEFT JOIN employees e ON e.id = s.employee_id AND e.company_id = s.company_id
            LEFT JOIN company_users u ON u.id = s.user_id
            WHERE s.company_id = CAST(:company_id AS uuid)
              AND s.status IN ('active', 'break')
              AND s.started_at < :limit
            ORDER BY s.started_at
        """),
        {"company_id": str(company_id), "limit": now - _hours(alert_hours)},
    )
    alerts = [{
        "employee_id": str(row.get("employee_id") or ""),
        "employee_name": row.get("name") or "Colaborador",
        "panel_type": row.get("panel_type") or "",
        "started_at": cutoff.aware(row["started_at"]).isoformat(),
        "hours_open": round((now - cutoff.aware(row["started_at"])).total_seconds() / 3600, 1),
    } for row in result.mappings().all()]
    seen = {a["employee_id"] for a in alerts if a["employee_id"]}
    result = await db.execute(
        text("""
            SELECT st.employee_id, st.check_in_at, e.full_name
            FROM workforce_attendance_status st
            JOIN employees e ON e.id = st.employee_id AND e.company_id = st.company_id
            WHERE st.company_id = CAST(:company_id AS uuid)
              AND st.status IN ('working', 'on_break')
              AND st.check_in_at < :limit
        """),
        {"company_id": str(company_id), "limit": now - _hours(alert_hours)},
    )
    for row in result.mappings().all():
        if str(row["employee_id"]) in seen:
            continue
        alerts.append({
            "employee_id": str(row["employee_id"]),
            "employee_name": row.get("full_name") or "Colaborador",
            "panel_type": "asistencia",
            "started_at": cutoff.aware(row["check_in_at"]).isoformat(),
            "hours_open": round((now - cutoff.aware(row["check_in_at"])).total_seconds() / 3600, 1),
        })
    return alerts


def _hours(value: float) -> timedelta:
    return timedelta(hours=float(value))


@router.get("/companies/{company_id}/dashboard")
async def sessions_dashboard(
    company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _actor: dict = Depends(require_session_admin),
) -> dict:
    policy = await cutoff.load_policy(db, company_id)
    tz = cutoff.zone(policy["timezone"])
    result = await db.execute(
        text("""
            SELECT * FROM workforce_session_closures
            WHERE company_id = CAST(:company_id AS uuid) AND status <> 'confirmed'
            ORDER BY employee_name, system_end_at
        """),
        {"company_id": str(company_id)},
    )
    closures = [cutoff.closure_payload(dict(row), tz) for row in result.mappings().all()]
    people: dict[str, dict] = {}
    for item in closures:  # un aviso por persona
        key = item["employee_id"] or item["employee_name"]
        person = people.setdefault(key, {"employee_id": item["employee_id"], "employee_name": item["employee_name"],
                                         "message": item["message"], "closures": []})
        person["closures"].append(item)
    now = datetime.now(timezone.utc)
    return {
        "policy": policy,
        "people": list(people.values()),
        "live_alerts": await _live_alerts(db, company_id, policy["alert_after_hours"], now),
    }


@router.get("/companies/{company_id}/closures/mine")
async def my_closures(
    company_id: uuid.UUID, db: AsyncSession = Depends(get_db), actor: dict = Depends(require_session_user),
) -> dict:
    if not actor["employee_id"]:
        return {"closures": []}
    tz = await _tz(db, company_id)
    result = await db.execute(
        text("""
            SELECT * FROM workforce_session_closures
            WHERE company_id = CAST(:company_id AS uuid) AND employee_id = CAST(:employee_id AS uuid)
              AND status <> 'confirmed'
            ORDER BY system_end_at
        """),
        {"company_id": str(company_id), "employee_id": actor["employee_id"]},
    )
    return {"closures": [cutoff.closure_payload(dict(row), tz) for row in result.mappings().all()]}


# ------------------------------------------------------------ acciones ---
@router.post("/companies/{company_id}/closures/{closure_id}/declare")
async def declare_real_end(
    company_id: uuid.UUID, closure_id: str, payload: dict | None = None,
    db: AsyncSession = Depends(get_db), actor: dict = Depends(require_session_user),
) -> dict:
    """El empleado propone su hora de salida; no cuenta hasta que la confirme el administrador."""
    row = await _closure(db, company_id, closure_id)
    if not actor["employee_id"] or actor["employee_id"] != str(row.get("employee_id") or ""):
        raise HTTPException(status_code=403, detail="Solo puedes proponer la hora de tus propios turnos.")
    if row["status"] == "confirmed":
        raise HTTPException(status_code=409, detail="La hora real ya fue registrada y no se puede cambiar.")
    tz = await _tz(db, company_id)
    end = _parse_end((payload or {}).get("end_at"), tz)
    _check_range(row, end)
    await db.execute(
        text("""
            UPDATE workforce_session_closures
               SET status = 'declared', declared_end_at = :end_at, declared_by_name = :name, declared_at = now()
             WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid) AND status <> 'confirmed'
        """),
        {"end_at": end, "name": f"{actor['name']} (declarada por el empleado)"[:180], "id": str(row["id"]),
         "company_id": str(company_id)},
    )
    await db.commit()
    return cutoff.closure_payload(await _closure(db, company_id, row["id"]), tz)


@router.post("/companies/{company_id}/closures/confirm")
async def confirm_real_end(
    company_id: uuid.UUID, payload: dict | None = None,
    db: AsyncSession = Depends(get_db), actor: dict = Depends(require_session_admin),
) -> dict:
    """Hora real de salida, UNA sola vez. Por id de cierre, o por el turno
    (source + session_ref) cuando es historico y aun no tiene fila."""
    data = payload or {}
    if data.get("closure_id"):
        row = await _closure(db, company_id, data["closure_id"])
    else:
        source, ref = str(data.get("source") or ""), str(data.get("session_ref") or "")
        row = await _closure_by_ref(db, company_id, source, ref) or await _create_from_source(db, company_id, source, ref)
    if row["status"] == "confirmed":
        raise HTTPException(status_code=409, detail="La hora real ya fue registrada y no se puede cambiar.")
    tz = await _tz(db, company_id)
    raw_end = data.get("real_end_at") or data.get("end_at")
    if raw_end:
        end = _parse_end(raw_end, tz)
    elif row.get("declared_end_at"):
        end = cutoff.aware(row["declared_end_at"])  # confirma la hora que propuso el empleado
    else:
        raise HTTPException(status_code=400, detail="Falta la hora real de salida.")
    _check_range(row, end)
    updated = await db.execute(
        text("""
            UPDATE workforce_session_closures
               SET status = 'confirmed', real_end_at = :end_at, confirmed_by_name = :name,
                   confirmed_by_user_id = :user_id, confirmed_at = now()
             WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid) AND status <> 'confirmed'
        """),
        {"end_at": end, "name": actor["name"][:180], "user_id": actor["id"], "id": str(row["id"]),
         "company_id": str(company_id)},
    )
    if not getattr(updated, "rowcount", 1):
        raise HTTPException(status_code=409, detail="La hora real ya fue registrada y no se puede cambiar.")
    await db.commit()
    return cutoff.closure_payload(await _closure(db, company_id, row["id"]), tz)


# ------------------------------------------------------------ politica ---
@router.get("/companies/{company_id}/policy")
async def get_policy(
    company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _actor: dict = Depends(require_session_admin),
) -> dict:
    return await cutoff.load_policy(db, company_id)


@router.put("/companies/{company_id}/policy")
async def save_policy(
    company_id: uuid.UUID, payload: dict | None = None,
    db: AsyncSession = Depends(get_db), _actor: dict = Depends(require_session_admin),
) -> dict:
    data = payload or {}
    try:
        cut = cutoff.parse_hhmm(data.get("cutoff_time"))
    except ValueError:
        raise HTTPException(status_code=400, detail="cutoff_time_invalid")
    try:
        hours = float(data.get("alert_after_hours") or cutoff.DEFAULT_ALERT_HOURS)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="alert_after_hours_invalid")
    if not 1 <= hours <= 24:
        raise HTTPException(status_code=400, detail="alert_after_hours_invalid")
    await db.execute(
        text("""
            INSERT INTO workforce_session_policy (company_id, cutoff_time, alert_after_hours, updated_at)
            VALUES (CAST(:company_id AS uuid), :cutoff_time, :hours, now())
            ON CONFLICT (company_id) DO UPDATE
               SET cutoff_time = EXCLUDED.cutoff_time, alert_after_hours = EXCLUDED.alert_after_hours, updated_at = now()
        """),
        {"company_id": str(company_id), "cutoff_time": cut.strftime("%H:%M"), "hours": hours},
    )
    await db.commit()
    return await cutoff.load_policy(db, company_id)
