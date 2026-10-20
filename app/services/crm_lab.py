"""CRM VELVET-LAB (interruptor crm_velvet_lab del modulo references).

Un mini panel de UN solo usuario en una tableta del taller: cada colaborador se
identifica con su PIN y registra turno y trabajo por referencia sin usuario propio.
Usa EXACTAMENTE las mismas funciones del bot de Telegram vivo (company_bots_v1:
asistencia de workforce, reference_work_sessions y reference_production_closures)
con source_channel = 'crm_lab', asi Nomina, Produccion y Referencias quedan iguales
vengan del bot o del CRM, y una sesion abierta por el bot se continua aqui (es la
misma fila) y al reves. Nunca hay dos sesiones activas: abrir una cierra la anterior.
Metricas siempre por lote o equipo; aqui no se calcula productividad individual.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import company_bots_v1 as bot

MODULE = "references"
FLAG = "crm_velvet_lab"
CHANNEL = "crm_lab"
PANEL_TYPE = "crm_lab"
MAX_ATTEMPTS = 5
LOCK = timedelta(minutes=5)
EMPLOYEE_TOKEN_MINUTES = 3
WORKING = {"working", "on_break"}


class CrmError(Exception):
    def __init__(self, code: str, status: int = 409, extra: Optional[dict] = None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra or {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return default if value is None else value


async def is_on(db: AsyncSession, company_id: Any) -> bool:
    row = (await db.execute(text("""
        SELECT cm.enabled, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id::text = :c AND lower(m.code) = :m LIMIT 1
    """), {"c": str(company_id), "m": MODULE})).mappings().first()
    return bool(row and row["enabled"] and _json(row["settings"], {}).get(FLAG) is True)


# ---------------------------------------------------------------- PIN
def valid_pin(pin: Any) -> str:
    clean = str(pin or "").strip()
    if not re.fullmatch(r"\d{4}", clean):
        raise CrmError("pin_de_4_digitos", 422)
    return clean


async def _employee(db: AsyncSession, company_id: str, employee_id: str) -> Optional[dict]:
    row = (await db.execute(text("""
        SELECT id::text AS employee_id, COALESCE(full_name, '') AS employee_name, COALESCE(role, '') AS employee_role
        FROM employees WHERE company_id::text = :c AND id::text = :e AND lower(COALESCE(status, 'active')) IN ('active', 'activo')
    """), {"c": company_id, "e": employee_id})).mappings().first()
    return dict(row) if row else None


async def set_pin(db: AsyncSession, company_id: str, employee_id: str, pin: Any, actor: str) -> dict:
    from app.services.auth_service import hash_password

    clean = valid_pin(pin)
    if not await _employee(db, company_id, employee_id):
        raise CrmError("colaborador_no_encontrado", 404)
    await db.execute(text("""
        INSERT INTO employee_crm_pins (company_id, employee_id, pin_hash, failed_attempts, locked_until, set_by, set_at)
        VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :h, 0, NULL, :by, now())
        ON CONFLICT (company_id, employee_id) DO UPDATE SET pin_hash = EXCLUDED.pin_hash, failed_attempts = 0, locked_until = NULL,
            set_by = EXCLUDED.set_by, set_at = now()
    """), {"c": company_id, "e": employee_id, "h": hash_password(clean), "by": actor[:200]})
    await log(db, company_id, employee_id, "", "pin_asignado", "PIN asignado o reiniciado", actor)
    await db.commit()
    return {"ok": True, "employee_id": employee_id, "has_pin": True}


async def clear_pin(db: AsyncSession, company_id: str, employee_id: str, actor: str) -> dict:
    await db.execute(text("DELETE FROM employee_crm_pins WHERE company_id::text = :c AND employee_id::text = :e"), {"c": company_id, "e": employee_id})
    await log(db, company_id, employee_id, "", "pin_quitado", "PIN quitado", actor)
    await db.commit()
    return {"ok": True, "employee_id": employee_id, "has_pin": False}


async def pin_status(db: AsyncSession, company_id: str) -> dict[str, dict]:
    rows = (await db.execute(text("""
        SELECT employee_id::text AS employee_id, set_at, locked_until FROM employee_crm_pins WHERE company_id::text = :c
    """), {"c": company_id})).mappings().all()
    return {r["employee_id"]: {"has_pin": True, "set_at": r["set_at"].isoformat() if r["set_at"] else None,
                               "locked": bool(r["locked_until"] and r["locked_until"] > _now())} for r in rows}


async def check_pin(db: AsyncSession, company_id: str, employee_id: str, pin: Any, now: Optional[datetime] = None) -> dict:
    """PIN correcto: devuelve al colaborador. 5 intentos fallidos: 5 minutos de bloqueo
    para ESE colaborador. Sin PIN: "Pide tu PIN al administrador"."""
    from app.services.auth_service import verify_password

    now = now or _now()
    employee = await _employee(db, company_id, employee_id)
    if not employee:
        raise CrmError("colaborador_no_encontrado", 404)
    row = (await db.execute(text("""
        SELECT pin_hash, failed_attempts, locked_until FROM employee_crm_pins
        WHERE company_id::text = :c AND employee_id::text = :e FOR UPDATE
    """), {"c": company_id, "e": employee_id})).mappings().first()
    if not row:
        await db.rollback()
        raise CrmError("sin_pin", 403)
    if row["locked_until"] and row["locked_until"] > now:
        await db.rollback()
        raise CrmError("pin_bloqueado", 423, {"seconds": int((row["locked_until"] - now).total_seconds()) + 1})
    clean = str(pin or "").strip()
    if re.fullmatch(r"\d{4}", clean) and verify_password(clean, row["pin_hash"]):
        await db.execute(text("UPDATE employee_crm_pins SET failed_attempts = 0, locked_until = NULL WHERE company_id::text = :c AND employee_id::text = :e"),
                         {"c": company_id, "e": employee_id})
        await db.commit()
        return employee
    attempts = int(row["failed_attempts"] or 0) + 1
    locked = attempts >= MAX_ATTEMPTS
    await db.execute(text("""
        UPDATE employee_crm_pins SET failed_attempts = :a, locked_until = :l WHERE company_id::text = :c AND employee_id::text = :e
    """), {"a": 0 if locked else attempts, "l": now + LOCK if locked else None, "c": company_id, "e": employee_id})
    await log(db, company_id, employee_id, employee["employee_name"], "pin_fallido", f"Intento {attempts}" + (" · bloqueado 5 min" if locked else ""), "")
    await db.commit()
    if locked:
        raise CrmError("pin_bloqueado", 423, {"seconds": int(LOCK.total_seconds())})
    raise CrmError("pin_incorrecto", 401, {"left": MAX_ATTEMPTS - attempts})


# ---------------------------------------------------------------- token corto del colaborador
def employee_token(company_id: str, employee_id: str, panel_user: str) -> str:
    from app.services.auth_service import create_access_token

    return create_access_token({"scope": "crm_lab_employee", "company_id": company_id, "employee_id": employee_id, "panel_user": panel_user},
                               expires_minutes=EMPLOYEE_TOKEN_MINUTES)


def employee_from_token(company_id: str, token: str) -> str:
    from app.services.auth_service import decode_access_token

    try:
        claims = decode_access_token(token)
    except Exception:  # noqa: BLE001 - vencido o alterado
        raise CrmError("pide_el_pin_otra_vez", 401) from None
    if claims.get("scope") != "crm_lab_employee" or str(claims.get("company_id")) != str(company_id) or not claims.get("employee_id"):
        raise CrmError("pide_el_pin_otra_vez", 401)
    return str(claims["employee_id"])


# ---------------------------------------------------------------- bitacora
async def log(db: AsyncSession, company_id: str, employee_id: Optional[str], employee_name: str, action: str, detail: str,
              panel_user: str, ip: str = "", device: str = "") -> None:
    await db.execute(text("""
        INSERT INTO crm_lab_log (company_id, employee_id, employee_name, action, detail, panel_user, ip, device, created_at)
        VALUES (CAST(:c AS uuid), CAST(NULLIF(:e, '') AS uuid), :n, :a, :d, :u, :ip, :dev, now())
    """), {"c": company_id, "e": employee_id or "", "n": (employee_name or "")[:200], "a": action[:40], "d": (detail or "")[:500],
           "u": (panel_user or "")[:200], "ip": (ip or "")[:120], "dev": (device or "")[:200]})


# ---------------------------------------------------------------- lectura
async def references(db: AsyncSession, company_id: str) -> list[dict]:
    """Referencias activas para el bot (bot_active), las mismas que ofrece Telegram,
    sin las archivadas y con su pendiente (meta - cerrado, el calculo de Referencias v2)."""
    from app.services import references_v2

    items = await bot.references(db, company_id)
    live = {r[0] for r in (await db.execute(text("""
        SELECT DISTINCT name FROM product_references
        WHERE company_id = :c AND bot_active IS TRUE AND COALESCE(archived, false) IS FALSE
    """), {"c": company_id})).all()}
    pending = {g["key"]: int(g["pending"]) for g in await references_v2.reference_groups(db, company_id)}
    return [{**r, "pending": pending.get(references_v2.group_key(r["name"]), 0)} for r in items if r["name"] in live]


async def team(db: AsyncSession, company_id: str, now: Optional[datetime] = None) -> dict:
    """Colaboradores activos con su estado y lo que hacen ahora (una consulta liviana)."""
    now = now or _now()
    rows = (await db.execute(text("""
        SELECT e.id::text AS employee_id, COALESCE(e.full_name, '') AS name, COALESCE(e.role, '') AS role,
               COALESCE(s.status, 'sin_turno') AS status,
               (SELECT max(COALESCE(ev.occurred_at, ev.created_at)) FROM workforce_attendance_events ev
                 WHERE ev.company_id = e.company_id AND ev.employee_id = e.id AND ev.event_type = 'check_in') AS shift_started,
               r.reference_id, r.reference_name, r.started_at AS reference_started,
               (p.employee_id IS NOT NULL) AS has_pin
        FROM employees e
        LEFT JOIN workforce_attendance_status s ON s.company_id = e.company_id AND s.employee_id = e.id
        LEFT JOIN LATERAL (
            SELECT reference_id, reference_name, started_at FROM reference_work_sessions w
            WHERE w.company_id = e.company_id::text AND w.employee_id = e.id::text AND w.status = 'active'
            ORDER BY started_at DESC LIMIT 1
        ) r ON TRUE
        LEFT JOIN employee_crm_pins p ON p.company_id = e.company_id AND p.employee_id = e.id
        WHERE e.company_id::text = :c AND lower(COALESCE(e.status, 'active')) IN ('active', 'activo')
        ORDER BY lower(COALESCE(e.full_name, ''))
    """), {"c": company_id})).mappings().all()
    people = []
    for r in rows:
        status = str(r["status"] or "").lower()
        status = status if status in WORKING else "sin_turno"
        since = r["reference_started"] if status in WORKING and r["reference_started"] else (r["shift_started"] if status in WORKING else None)
        people.append({"employee_id": r["employee_id"], "name": r["name"], "role": r["role"], "status": status, "has_pin": bool(r["has_pin"]),
                       "reference_id": r["reference_id"] if status in WORKING else None, "reference_name": r["reference_name"] if status in WORKING else None,
                       "since": since.isoformat() if since else None,
                       "elapsed_minutes": int((now - since).total_seconds() // 60) if since else None})
    working = sum(1 for p in people if p["status"] == "working")
    paused = sum(1 for p in people if p["status"] == "on_break")
    return {"now": now.isoformat(), "working": working, "paused": paused, "people": people,
            "live": [p for p in people if p["status"] in WORKING]}


async def sizes(db: AsyncSession, company_id: str, reference_id: str) -> list[dict]:
    """Tallas de la referencia (las mismas filas que ofrece el bot) con su pendiente
    = meta (suma de cortes) - cerrado, el mismo calculo de Referencias v2."""
    from app.services import references_v2

    rows = await bot.sizes_by_reference_id(db, company_id, reference_id)
    pending: dict[str, int] = {}
    meta: dict[str, int] = {}
    for g in await references_v2.reference_groups(db, company_id):
        for line in g["lines"]:
            if line.get("reference_id"):
                pending[line["reference_id"]] = int(line["pending"])
                meta[line["reference_id"]] = int(line["meta"])
    return [{"reference_id": r["id"], "name": r["name"], "size": r["size"], "pending": pending.get(r["id"], 0), "meta": meta.get(r["id"], 0)}
            for r in rows]


async def person(db: AsyncSession, company_id: str, employee_id: str) -> dict:
    employee = await _employee(db, company_id, employee_id)
    if not employee:
        raise CrmError("colaborador_no_encontrado", 404)
    status = await bot.workforce_status(db, company_id, employee_id)
    status = status if status in WORKING else "sin_turno"
    active = await bot.active_reference_session(db, company_id, employee_id)
    out = {"employee_id": employee_id, "name": employee["employee_name"], "status": status, "reference": None, "sizes": []}
    if active and status in WORKING:
        out["reference"] = {"id": active["reference_id"], "name": active["reference_name"],
                            "started_at": active["started_at"].isoformat() if active.get("started_at") else None}
        if active.get("reference_id"):
            out["sizes"] = await sizes(db, company_id, active["reference_id"])
    return out


# ---------------------------------------------------------------- acciones (mismas funciones del bot)
async def act(db: AsyncSession, company_id: str, employee_id: str, action: str, payload: dict, panel_user: str,
              ip: str = "", device: str = "") -> dict:
    employee = await _employee(db, company_id, employee_id)
    if not employee:
        raise CrmError("colaborador_no_encontrado", 404)
    # Un toque a la vez por colaborador: dos toques seguidos nunca duplican turno ni sesion.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"crm_lab:{company_id}:{employee_id}"})
    status = await bot.workforce_status(db, company_id, employee_id)
    status = status if status in WORKING else "sin_turno"
    meta = {"panel_user": panel_user, "ip": ip, "device": device}
    detail = ""

    async def ref_or_404(ref_id: Any) -> dict:
        ref = await bot.reference_by_id(db, company_id, str(ref_id or ""))
        if not ref:
            raise CrmError("referencia_no_activa", 404)
        return ref

    if action == "start_shift":
        if status in WORKING:
            raise CrmError("turno_ya_iniciado")
        # 056J: desde el CRM el turno se inicia SIEMPRE en una referencia (turno y sesion en
        # la misma transaccion: si algo falla no se confirma ninguno). El bot no pasa por aqui.
        if not payload.get("reference_id"):
            raise CrmError("elige_una_referencia", 400)
        ref = await ref_or_404(payload.get("reference_id"))
        await bot.insert_attendance_event(db, company_id=company_id, employee=employee, event_type="check_in", event_label="Inicio de turno",
                                          status_after="working", detail=f"Referencia inicial: {ref['name']}" if ref else "",
                                          metadata=meta, source_channel=CHANNEL)
        if ref:
            await bot.open_reference_session(db, company_id=company_id, employee=employee, telegram_user_id="", reference=ref,
                                             close_status="closed_by_new_start", source_channel=CHANNEL)
        detail = f"Inicio de turno{(' · ' + ref['name']) if ref else ''}"
    elif action == "pause":
        if status != "working":
            raise CrmError("no_esta_trabajando")
        await bot.insert_attendance_event(db, company_id=company_id, employee=employee, event_type="break_start", event_label="Pausa",
                                          status_after="on_break", metadata=meta, source_channel=CHANNEL)
        detail = "Pausa"
    elif action == "resume":
        if status != "on_break":
            raise CrmError("no_esta_en_pausa")
        await bot.insert_attendance_event(db, company_id=company_id, employee=employee, event_type="break_end", event_label="Retorno",
                                          status_after="working", metadata=meta, source_channel=CHANNEL)
        detail = "Reanudar"
    elif action == "end_shift":
        if status not in WORKING:
            raise CrmError("sin_turno_abierto")
        await bot.insert_attendance_event(db, company_id=company_id, employee=employee, event_type="check_out", event_label="Finalización de turno",
                                          status_after="checked_out", metadata=meta, source_channel=CHANNEL)
        await bot.close_active_reference_session(db, company_id, employee_id, "ended_with_shift")
        detail = "Fin de turno"
    elif action in ("start_reference", "switch_reference"):
        if status not in WORKING:
            raise CrmError("inicia_tu_turno")
        ref = await ref_or_404(payload.get("reference_id"))
        previous = await bot.active_reference_session(db, company_id, employee_id)
        if previous and str(previous.get("reference_id") or "") == str(ref["id"]):
            raise CrmError("ya_en_esa_referencia")
        if previous:
            # Cambio de referencia: lo mismo que el bot (cierra "switched" y deja el evento).
            await bot.open_reference_session(db, company_id=company_id, employee=employee, telegram_user_id="", reference=ref,
                                             close_status="switched", source_channel=CHANNEL)
            await bot.insert_attendance_event(
                db, company_id=company_id, employee=employee, event_type="reference_switch", event_label="Cambio de referencia",
                status_after=status, detail=f"Cambio de referencia: {previous.get('reference_name') or 'Sin referencia'} → {ref['name']}",
                metadata={**meta, "reference_id": ref["id"], "reference_name": ref["name"], "previous_reference_id": previous.get("reference_id") or "",
                          "previous_reference_name": previous.get("reference_name") or "", "previous_reference_session_id": str(previous.get("id") or "")},
                source_channel=CHANNEL)
            detail = f"Cambio de referencia: {previous.get('reference_name') or '—'} → {ref['name']}"
        else:
            await bot.open_reference_session(db, company_id=company_id, employee=employee, telegram_user_id="", reference=ref,
                                             close_status="closed_by_new_start", source_channel=CHANNEL)
            detail = f"Inicio de referencia: {ref['name']}"
    elif action == "close":
        try:
            qty = int(payload.get("quantity"))
        except (TypeError, ValueError):
            raise CrmError("cantidad_invalida", 422) from None
        if qty <= 0 or qty > 100000:
            raise CrmError("cantidad_invalida", 422)
        size_ref = await ref_or_404(payload.get("size_reference_id"))
        pending = next((s["pending"] for s in await sizes(db, company_id, size_ref["id"]) if s["reference_id"] == size_ref["id"]), 0)
        if qty > pending and payload.get("confirm") is not True:
            raise CrmError("supera_el_pendiente", 409, {"pending": pending})
        await bot.save_production_close(db, company_id=company_id, employee=employee, telegram_user_id="", reference=size_ref,
                                        quantity_finished=qty, source_channel=CHANNEL)
        detail = f"Cerrar prendas: {size_ref['name']} / talla {size_ref['size']} × {qty}" + (f" (pendiente {pending}, confirmado)" if qty > pending else "")
    else:
        raise CrmError("accion_invalida", 422)
    await log(db, company_id, employee_id, employee["employee_name"], action, detail, panel_user, ip, device)
    await db.commit()
    return await person(db, company_id, employee_id)
