"""Lugares de trabajo por empresa (interruptor work_locations, modulo workforce).

Apagado por defecto: sin el interruptor los endpoints responden 404 y Personal /
CRM Campo siguen exactamente igual. Hoy solo VOLTAGE (f1e8f774-...) lo tiene.

- Lugares: nombre, sigla, zona horaria IANA, activo y orden. No se borran, se
  desactivan (el historial y la nomina los siguen nombrando).
- employees.work_location_id: lugar actual (NULL = "Sin asignar").
- work_location_changes: cada traslado con lugar anterior, nuevo, fecha y quien.
  location_on() responde en que lugar estaba alguien en una fecha (para nomina).
- board(): CRM Campo agrupado por lugar con pocas consultas fijas (empleados,
  eventos de los ultimos dias, ultima ubicacion GPS) sin importar cuantas
  personas haya. El tiempo trabajado usa las MISMAS funciones del CRM de siempre
  (crm_core_v1: inicio de turno, pausas, conectado - pausas).

Toda consulta filtra por company_id.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

KEY = "work_locations"
MODULE = "workforce"
NONE_KEY = "none"
EVENT_WINDOW_DAYS = 4  # el corte diario cierra turnos; 4 dias cubren turnos largos
MAX_LOCATIONS = 20

OWNER_ROLES = {"company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario"}
DIRECTOR_ROLES = {"gerencia", "director", "gerente", "manager", "management"}
SUPERVISOR_ROLES = {"supervisor"}
# Ver la pantalla (Personal y CRM Campo): los mismos roles de lectura del portal.
READ_ROLES = OWNER_ROLES | DIRECTOR_ROLES | SUPERVISOR_ROLES | {
    "operator", "operador", "operario", "staff", "viewer", "consulta", "tesoreria", "treasury"}
# Asignar lugar a empleados: quien edita Personal (dueno, direccion, supervisor).
ASSIGN_ROLES = OWNER_ROLES | DIRECTOR_ROLES | SUPERVISOR_ROLES
# Administrar lugares: solo dueno / admin de la empresa (y Admin V2).
MANAGE_ROLES = OWNER_ROLES


class Invalid(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


# ------------------------------------------------------------------ reglas puras
def settings_dict(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def switch_on(enabled: Any, settings: Any) -> bool:
    return enabled is True and settings_dict(settings).get(KEY) is True


def role_of(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def valid_timezone(value: Any) -> str:
    tz = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+\-]+){1,2}", tz):
        raise Invalid("timezone", "Zona horaria no válida (ej: America/New_York).")
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise Invalid("timezone", f"Zona horaria desconocida: {tz}.") from None
    return tz


def validate_locations(body: Any, existing_ids: Iterable[str]) -> list[dict]:
    """Cuerpo de "Administrar lugares" -> filas limpias. No borra: los lugares
    existentes que no vengan se dejan como estan."""
    items = body.get("locations") if isinstance(body, dict) else None
    if not isinstance(items, list) or not items:
        raise Invalid("locations", "Envía la lista de lugares.")
    if len(items) > MAX_LOCATIONS:
        raise Invalid("locations", f"Máximo {MAX_LOCATIONS} lugares.")
    known = {str(i) for i in existing_ids}
    out: list[dict] = []
    names: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise Invalid("locations", "Lugar no válido.")
        name = re.sub(r"\s+", " ", str(item.get("name") or "")).strip()
        if len(name) < 2 or len(name) > 80:
            raise Invalid("name", "Cada lugar necesita un nombre de 2 a 80 caracteres.")
        if name.lower() in names:
            raise Invalid("name", f"El lugar «{name}» está repetido.")
        names.add(name.lower())
        code = re.sub(r"[^A-Za-z0-9]", "", str(item.get("code") or "")).upper()[:8] or None
        lid = str(item.get("id") or "").strip() or None
        if lid and lid not in known:
            raise Invalid("id", "Ese lugar no es de esta empresa.")
        out.append({
            "id": lid, "name": name, "code": code,
            "timezone": valid_timezone(item.get("timezone")),
            "is_active": item.get("is_active") is not False,
            "sort_order": index + 1,
        })
    if not any(row["is_active"] for row in out):
        raise Invalid("is_active", "Debe quedar al menos un lugar activo.")
    return out


def location_on(changes: list[dict], current: str | None, at: datetime) -> str | None:
    """Lugar de un empleado en la fecha `at`, con su historial de traslados
    (lista de {to_location_id, from_location_id, changed_at}). Antes del primer
    traslado vale el lugar anterior de ese traslado."""
    ordered = sorted(changes, key=lambda c: c["changed_at"])
    if not ordered:
        return current
    place = ordered[0].get("from_location_id")
    for change in ordered:
        if change["changed_at"] <= at:
            place = change.get("to_location_id")
        else:
            break
    return place


STATUS_ORDER = {"working": 0, "on_break": 1}


def sort_people(rows: list[dict]) -> list[dict]:
    """Trabajando, en pausa, sin turno; alfabetico dentro de cada grupo."""
    return sorted(rows, key=lambda r: (STATUS_ORDER.get(r["core"]["status"], 2), str(r.get("employee_name") or "").casefold()))


def gps_place(gps: dict | None) -> str:
    """inside | outside | unconfigured (sin geocerca) | none (sin ubicacion)."""
    if not gps:
        return "none"
    status = str(gps.get("gps_status") or "")
    return status if status in {"inside", "outside"} else "unconfigured"


def counts(rows: list[dict]) -> dict:
    st = [r["core"]["status"] for r in rows]
    return {
        "total": len(rows),
        "working": st.count("working"),
        "on_break": st.count("on_break"),
        "no_shift": sum(1 for s in st if s not in {"working", "on_break"}),
        "in_perimeter": sum(1 for r in rows if r.get("gps_place") == "inside"),
    }


def group_rows(rows: list[dict], locations: list[dict]) -> list[dict]:
    """Una seccion por lugar activo (y por lugar inactivo que aun tenga gente),
    en el orden configurado; al final "Sin asignar" si hay alguien sin lugar o
    con un lugar que ya no existe. Nadie se pierde."""
    known = {loc["id"]: loc for loc in locations}
    buckets: dict[str, list[dict]] = {loc["id"]: [] for loc in locations}
    buckets[NONE_KEY] = []
    for row in rows:
        lid = row.get("work_location_id")
        buckets[lid if lid in known else NONE_KEY].append(row)
    groups = []
    for loc in sorted(locations, key=lambda l: (l["sort_order"], l["name"].casefold())):
        people = buckets[loc["id"]]
        if not loc["is_active"] and not people:
            continue
        groups.append({
            "key": loc["id"], "name": loc["name"], "code": loc.get("code"), "timezone": loc["timezone"],
            "is_active": loc["is_active"],
            "supervisors": sorted({p["employee_name"] for p in people if p.get("is_supervisor")}, key=str.casefold),
            "counts": counts(people), "people": sort_people(people),
        })
    if buckets[NONE_KEY]:
        people = buckets[NONE_KEY]
        groups.append({
            "key": NONE_KEY, "name": "Sin asignar", "code": None, "timezone": None, "is_active": True,
            "supervisors": sorted({p["employee_name"] for p in people if p.get("is_supervisor")}, key=str.casefold),
            "counts": counts(people), "people": sort_people(people),
        })
    return groups


def location_out(row: Any) -> dict:
    r = dict(row)
    return {"id": str(r["id"]), "name": r["name"], "code": r.get("code"), "timezone": r["timezone"],
            "is_active": bool(r["is_active"]), "sort_order": int(r.get("sort_order") or 0)}


# ------------------------------------------------------------------ datos
async def module_state(db: AsyncSession, company_id: Any) -> tuple[bool, dict]:
    row = (await db.execute(text("""
        SELECT cm.enabled, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:c AS uuid) AND m.code = :m LIMIT 1
    """), {"c": str(company_id), "m": MODULE})).first()
    if not row:
        return False, {}
    return row[0] is True, settings_dict(row[1])


async def is_on(db: AsyncSession, company_id: Any) -> bool:
    enabled, settings = await module_state(db, company_id)
    return switch_on(enabled, settings)


async def list_locations(db: AsyncSession, company_id: Any) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id, name, code, timezone, is_active, sort_order FROM work_locations
        WHERE company_id = CAST(:c AS uuid) ORDER BY sort_order, lower(name)
    """), {"c": str(company_id)})).mappings().all()
    return [location_out(r) for r in rows]


async def assignments(db: AsyncSession, company_id: Any) -> dict[str, str | None]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, work_location_id::text AS lid FROM employees WHERE company_id = CAST(:c AS uuid)
    """), {"c": str(company_id)})).mappings().all()
    return {r["id"]: r["lid"] for r in rows}


async def save_locations(db: AsyncSession, company_id: Any, body: Any) -> list[dict]:
    current = await list_locations(db, company_id)
    rows = validate_locations(body, [loc["id"] for loc in current])
    sent = {r["id"] for r in rows if r["id"]}
    # Los que no vinieron quedan al final, en su orden de siempre (no se borran).
    tail = [loc for loc in current if loc["id"] not in sent]
    taken = {r["name"].lower() for r in rows}
    for loc in tail:
        if loc["name"].lower() in taken:
            raise Invalid("name", f"El lugar «{loc['name']}» ya existe.")
    for row in rows:
        params = {"c": str(company_id), "n": row["name"], "k": row["code"], "tz": row["timezone"], "a": row["is_active"], "o": row["sort_order"]}
        if row["id"]:
            await db.execute(text("""
                UPDATE work_locations SET name = :n, code = :k, timezone = :tz, is_active = :a, sort_order = :o, updated_at = now()
                WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
            """), {**params, "i": row["id"]})
        else:
            await db.execute(text("""
                INSERT INTO work_locations (company_id, name, code, timezone, is_active, sort_order)
                VALUES (CAST(:c AS uuid), :n, :k, :tz, :a, :o)
            """), params)
    for offset, loc in enumerate(tail, start=len(rows) + 1):
        await db.execute(text("UPDATE work_locations SET sort_order = :o WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)"),
                         {"o": offset, "i": loc["id"], "c": str(company_id)})
    await db.commit()
    return await list_locations(db, company_id)


async def assign(db: AsyncSession, company_id: Any, employee_ids: Any, location_id: Any, *,
                 actor: str, actor_user_id: str | None = None, source: str = "personal") -> dict:
    """Asigna (o quita, con None) el lugar a varios empleados de la empresa y
    deja un registro de traslado por cada uno que cambio. No toca otros campos."""
    if not isinstance(employee_ids, list) or not employee_ids:
        raise Invalid("employee_ids", "Elige al menos un empleado.")
    if len(employee_ids) > 500:
        raise Invalid("employee_ids", "Máximo 500 empleados a la vez.")
    ids = sorted({str(i).strip() for i in employee_ids if str(i or "").strip()})
    lid = str(location_id).strip() if location_id not in (None, "", NONE_KEY) else None
    locations = {loc["id"]: loc for loc in await list_locations(db, company_id)}
    if lid is not None:
        if lid not in locations:
            raise Invalid("work_location_id", "Ese lugar no es de esta empresa.")
        if not locations[lid]["is_active"]:
            raise Invalid("work_location_id", "Ese lugar está desactivado.")
    rows = (await db.execute(text("""
        SELECT id::text AS id, work_location_id::text AS lid FROM employees
        WHERE company_id = CAST(:c AS uuid) AND id::text = ANY(:ids)
    """), {"c": str(company_id), "ids": ids})).mappings().all()
    if len(rows) != len(ids):
        raise Invalid("employee_ids", "Algún empleado no es de esta empresa.")
    changed = 0
    for row in rows:
        if row["lid"] == lid:
            continue
        await db.execute(text("""
            UPDATE employees SET work_location_id = CAST(:l AS uuid) WHERE id = CAST(:e AS uuid) AND company_id = CAST(:c AS uuid)
        """), {"l": lid, "e": row["id"], "c": str(company_id)})
        await db.execute(text("""
            INSERT INTO work_location_changes (company_id, employee_id, from_location_id, to_location_id, from_name, to_name,
                                               changed_by, changed_by_user_id, source)
            VALUES (CAST(:c AS uuid), CAST(:e AS uuid), CAST(:f AS uuid), CAST(:t AS uuid), :fn, :tn, :by, CAST(:uid AS uuid), :src)
        """), {"c": str(company_id), "e": row["id"], "f": row["lid"], "t": lid,
               "fn": (locations.get(row["lid"]) or {}).get("name") if row["lid"] else None,
               "tn": (locations.get(lid) or {}).get("name") if lid else None,
               "by": str(actor or "")[:200] or None, "uid": actor_user_id, "src": source[:40]})
        changed += 1
    await db.commit()
    return {"changed": changed, "unchanged": len(rows) - changed, "work_location_id": lid}


async def history(db: AsyncSession, company_id: Any, employee_id: Any) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, from_location_id::text AS from_location_id, to_location_id::text AS to_location_id,
               from_name, to_name, changed_at, changed_by, source
        FROM work_location_changes
        WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid)
        ORDER BY changed_at DESC LIMIT 100
    """), {"c": str(company_id), "e": str(employee_id)})).mappings().all()
    return [{**dict(r), "changed_at": r["changed_at"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z")} for r in rows]


# ------------------------------------------------------------------ CRM Campo
async def _board_employees(db: AsyncSession, company_id: str) -> list[dict]:
    has_status = bool((await db.execute(text("SELECT to_regclass('workforce_attendance_status')"))).scalar())
    status_sql = ("COALESCE(s.status, 'sin_turno') AS work_status, s.last_event_at AS status_started_at, COALESCE(s.last_event_type, '') AS last_event_type"
                  if has_status else "'sin_turno' AS work_status, NULL::timestamptz AS status_started_at, '' AS last_event_type")
    join = "LEFT JOIN workforce_attendance_status s ON s.company_id = e.company_id AND s.employee_id = e.id" if has_status else ""
    rows = (await db.execute(text(f"""
        SELECT e.id::text AS employee_id, COALESCE(e.full_name, '') AS employee_name, COALESCE(e.role, '') AS employee_role,
               COALESCE(e.telegram_user_id::text, '') AS telegram_user_id, e.work_location_id::text AS work_location_id, {status_sql}
        FROM employees e {join}
        WHERE e.company_id = CAST(:c AS uuid) AND lower(COALESCE(e.status, 'active')) IN ('active', 'activo')
        ORDER BY employee_name
    """), {"c": company_id})).mappings().all()
    return [dict(r) for r in rows]


async def _board_events(db: AsyncSession, company_id: str, since: datetime) -> list[dict]:
    from app.api.v1.endpoints import crm_core_v1 as crm

    kinds = sorted(crm.START_EVENTS | crm.PAUSE_START_EVENTS | crm.PAUSE_END_EVENTS | crm.END_EVENTS)
    rows = (await db.execute(text("""
        SELECT employee_id::text AS employee_id, COALESCE(telegram_user_id::text, '') AS telegram_user_id,
               lower(COALESCE(employee_name, '')) AS employee_name, lower(COALESCE(event_type, '')) AS event_type,
               COALESCE(occurred_at, created_at) AS event_at
        FROM workforce_attendance_events
        WHERE company_id = CAST(:c AS uuid) AND COALESCE(occurred_at, created_at) >= :since
          AND lower(COALESCE(event_type, '')) = ANY(:kinds)
        ORDER BY COALESCE(occurred_at, created_at) ASC
        LIMIT 20000
    """), {"c": company_id, "since": since, "kinds": kinds})).mappings().all()
    return [dict(r) for r in rows]


def _events_by_employee(events: list[dict], employees: list[dict]) -> dict[str, list[dict]]:
    """Mismo emparejamiento que el CRM de siempre: por id, Telegram o nombre."""
    by_id = {e["employee_id"]: e["employee_id"] for e in employees}
    by_tg = {e["telegram_user_id"]: e["employee_id"] for e in employees if e["telegram_user_id"]}
    by_name = {e["employee_name"].lower(): e["employee_id"] for e in employees if e["employee_name"]}
    out: dict[str, list[dict]] = {e["employee_id"]: [] for e in employees}
    for ev in events:
        eid = by_id.get(ev.get("employee_id") or "") or by_tg.get(ev.get("telegram_user_id") or "") or by_name.get(ev.get("employee_name") or "")
        if eid and isinstance(ev.get("event_at"), datetime):
            at = ev["event_at"] if ev["event_at"].tzinfo else ev["event_at"].replace(tzinfo=timezone.utc)
            out[eid].append({"event_type": ev["event_type"], "event_at": at.astimezone(timezone.utc)})
    return out


def person_row(emp: dict, events: list[dict], gps: dict | None, modules: set[str], now_value: datetime,
               role_label: str | None = None) -> dict:
    """Fila del tablero con la forma del snapshot del CRM (core, gps, adapters),
    para que el detalle de siempre la pueda dibujar."""
    from app.api.v1.endpoints import crm_core_v1 as crm

    status = crm.normalize_status(emp.get("work_status"))
    status_started_at = crm.parse_dt(emp.get("status_started_at"))
    shift_start = None
    if status in {"working", "on_break"}:
        shift_start = crm.latest_shift_start_from_events(events) or status_started_at
    pauses, current_pause = crm.pause_intervals_from_events(
        events, shift_start=shift_start, current_status=status, status_started_at=status_started_at, now_value=now_value)
    effective = crm.effective_seconds_for_interval(shift_start, now_value, pauses) if status in {"working", "on_break"} else 0
    adapters = []
    if "gps" in modules:
        items = []
        if gps:
            items.append({**gps, "title": gps.get("zone_name") or ("Fuera de zona autorizada" if gps.get("gps_status") == "outside" else "Sin ubicación"),
                          "status": gps.get("gps_status") or "unconfigured"})
        adapters.append({"code": "gps", "title": "GPS", "enabled": True, "items": items,
                         "placeholder": "GPS activo para ubicación, rutas y perímetros."})
    if "materials" in modules:
        adapters.append({"code": "materials", "title": "Materiales", "enabled": True, "items": [],
                         "placeholder": "Materiales activo para solicitudes, entregas y devoluciones."})
    if "inventory" in modules:
        adapters.append({"code": "inventory", "title": "Inventario", "enabled": True, "items": [],
                         "placeholder": "Inventario activo para stock y disponibilidad."})
    return {
        "employee_id": emp["employee_id"],
        "employee_name": emp.get("employee_name") or "Empleado",
        "employee_role": role_label if role_label is not None else emp.get("employee_role") or "",
        "role_code": role_of(emp.get("employee_role")),
        "is_supervisor": role_of(emp.get("employee_role")) in SUPERVISOR_ROLES,
        "work_location_id": emp.get("work_location_id"),
        "gps": gps,
        "gps_place": gps_place(gps) if "gps" in modules else "none",
        "core": {
            "status": status,
            "status_label": crm.status_label(status),
            "last_event_type": emp.get("last_event_type") or "",
            "shift_started_at": crm.dt_text(shift_start),
            "status_started_at": crm.dt_text(status_started_at),
            "pause_started_at": crm.dt_text(current_pause),
            "shift_effective_seconds": effective,
            "pause_accumulated_seconds": sum(crm.seconds_between(a, b) for a, b in pauses),
            "current_pause_seconds": crm.seconds_between(current_pause, now_value) if current_pause else 0,
            "shift_running": status == "working",
            "pause_running": status == "on_break",
            "time_rule": "pause_excluded_from_shift_payroll_production",
        },
        "adapters": adapters,
    }


async def board(db: AsyncSession, company_id: Any, now_value: datetime | None = None) -> dict:
    from app.api.v1.endpoints import crm_core_v1 as crm
    from app.services import employee_roles

    cid = str(company_id)
    now_value = now_value or datetime.now(timezone.utc)
    modules = await crm.active_modules(db, cid)
    locations = await list_locations(db, cid)
    employees = await _board_employees(db, cid)
    events = await _board_events(db, cid, now_value - timedelta(days=EVENT_WINDOW_DAYS))
    gps_by = await crm.crm_gps_people_by_employee(db, cid) if "gps" in modules else {}
    config = await employee_roles.load_config(db, cid)
    by_emp = _events_by_employee(events, employees)
    rows = [person_row(e, by_emp.get(e["employee_id"], []), gps_by.get(e["employee_id"]), modules, now_value,
                       employee_roles.display(config, e.get("employee_role")) if config else None) for e in employees]
    total = counts(rows)
    summary = {
        "employees_total": total["total"], "active_now": total["working"], "on_break": total["on_break"], "out": total["no_shift"],
        "gps_adapter": "gps" in modules,
        "gps_sent_location": sum(1 for r in rows if r.get("gps")),
        "gps_inside": total["in_perimeter"],
        "gps_outside": sum(1 for r in rows if r.get("gps_place") == "outside"),
        "materials_adapter": "materials" in modules, "inventory_adapter": "inventory" in modules,
    }
    return {
        "ok": True, "company_id": cid, "server_time": crm.dt_text(now_value), "active_modules": sorted(modules),
        "locations": locations, "summary": summary, "groups": group_rows(rows, locations),
    }
