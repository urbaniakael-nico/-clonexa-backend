"""Mini panel "Lider de operacion": CRM Campo y Reportes de UNA operacion.

Disponible solo con los interruptores work_locations y reports_board encendidos (hoy VOLTAGE).
Reutiliza el Board de gerencia (reports_board.build): mismas horas que Nomina y sin dinero.

Reglas que este modulo sostiene en el servidor:
- La operacion sale de la sesion (work_location_id del token), nunca de lo que pida el navegador.
- Solo entra un empleado activo con rol Supervisor asignado a ESA operacion, y se revisa en cada
  peticion: si cambia de rol o de lugar, pierde el acceso de inmediato.
- Lista blanca: con una sesion de lider solo responden las rutas de request_allowed. Todo lo demas
  (Nomina, tarifas, horas, la otra operacion) es 403 en app/main.py y en auth_service. Sus dos
  unicas escrituras estan en lider_pin: marcar con PIN y finalizar ahora un turno.

Toda consulta filtra por company_id.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import reports_board, us_payroll, us_time, work_location_geo as geo, work_locations
from app.services.auth_service import LEADER_PANEL_TYPE as PANEL_TYPE

LABEL = "Líder de operación"
CRM_DAYS = 7  # de cuantos dias atras sale la "ultima marca" de CRM Campo
WEEK_DAYS = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
GEO_LABEL = {"inside": "En perímetro", "outside": "Fuera de perímetro", "unconfigured": "Sin perímetro", "none": "Sin ubicación", "adjusted": "Ajuste manual"}

_READ_ROUTE = re.compile(r"^/api/v1/lider-operacion/companies/[^/]+/(inicio|crm|reportes|crm/lista\.pdf|reportes/export\.pdf)/?$")
# Sus unicas escrituras: marcar con PIN y finalizar ahora un turno de su operacion (lider_pin).
_WRITE_ROUTE = re.compile(r"^/api/v1/lider-operacion/companies/[^/]+/(pin/verificar|pin/marcar|crm/[^/]+/finalizar)/?$")
_LOGOUT = "/api/v1/auth/logout"


# ------------------------------------------------------------------ reglas puras
def request_allowed(method: str, path: str) -> bool:
    """Lo unico que responde una sesion de lider: sus lecturas, sus dos escrituras y cerrar su sesion."""
    verb = str(method or "").upper()
    if verb == "GET":
        return bool(_READ_ROUTE.match(path or ""))
    return verb == "POST" and ((path or "").rstrip("/") == _LOGOUT or bool(_WRITE_ROUTE.match(path or "")))


def slug(value: Any) -> str:
    plain = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(c for c in plain if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def denied_message(place_name: Any) -> str:
    return f"Este panel es solo para el líder de {place_name}"


def resolve_place(places: list[dict], wanted: Any) -> Optional[dict]:
    """La operacion de un enlace: por nombre (lugar=virginia), sigla o id."""
    key = slug(wanted)
    if not key:
        return None
    for place in places:
        if key in (place["slug"], place["id"].casefold(), slug(place.get("code"))):
            return place
    return None


def leader_settings(user: Any) -> dict:
    raw = getattr(user, "settings_json", None)
    mini = raw.get("mini_panel") if isinstance(raw, dict) else None
    return mini if isinstance(mini, dict) else {}


def is_leader_of(user: Any, place_id: str) -> bool:
    mini = leader_settings(user)
    return (mini.get("enabled") is True and str(mini.get("type") or "") == PANEL_TYPE
            and str(mini.get("work_location_id") or "") == str(place_id) and bool(mini.get("employee_id")))


def entry_link(company_id: Any, place: dict) -> str:
    return f"/mini-panel/login?company_id={company_id}&type={PANEL_TYPE}&lugar={place['slug']}"


def week_of(day: date, week_start_day: Any) -> tuple[date, date]:
    wanted = str(week_start_day or "sunday").strip().lower()
    first = WEEK_DAYS.index(wanted) if wanted in WEEK_DAYS else 0
    back = ((day.weekday() + 1) % 7 - first) % 7  # weekday(): lunes=0; WEEK_DAYS: domingo=0
    start = day - timedelta(days=back)
    return start, start + timedelta(days=6)


def people_state(person: dict) -> str:
    """El chip de CRM Campo: "Termino hoy" tambien es Sin turno."""
    state = (person.get("now") or {}).get("state")
    return state if state in ("working", "on_break", "to_confirm") else "no_shift"


def count_states(people: list[dict]) -> dict:
    states = [people_state(p) for p in people]
    return {"total": len(states), "working": states.count("working"), "on_break": states.count("on_break"),
            "no_shift": states.count("no_shift"), "to_confirm": states.count("to_confirm")}


def last_mark_of(person: dict) -> Optional[dict]:
    """La marca mas reciente con su ubicacion corta (perimetro o estado), sin coordenadas."""
    marks = [m for d in person.get("days") or [] for s in d.get("shifts") or [] for m in reports_board._marks_of(s)]
    if not marks:
        return None
    last = max(marks, key=lambda m: m["at"])
    status = last.get("s")
    place = last.get("n") or GEO_LABEL.get(status or "", "")
    return {"k": last["k"], "label": reports_board.MARK_LABEL[last["k"]], "t": last["t"], "d": last["d"], "a": last["a"], "at": last["at"], "place": place, "s": status, "o": last.get("o") or ""}


def _brief_mark(mark: dict) -> dict:
    return {"t": mark["t"], "d": mark["d"], "a": mark["a"], "o": mark.get("o") or ""}


def latest_shift(person: dict, since: Optional[dict]) -> Optional[dict]:
    """El detalle de la persona: su turno mas reciente con entrada, pausas y salida, sin coordenadas."""
    shifts = [s for d in person.get("days") or [] for s in d.get("shifts") or [] if s.get("in")]
    last = max(shifts, key=lambda s: s["in"]["at"]) if shifts else None
    if since and (not last or str(last["in"]["at"]) < str(since.get("at") or "")):
        return {"in": _brief_mark(since), "out": None, "pauses": []}  # entro en este mismo minuto
    if not last:
        return None
    pauses = [{"start": p["start"]["t"], "end": p["end"]["t"] if p.get("end") else None, "minutes": int(p.get("minutes") or 0), "o": p["start"].get("o") or ""}
              for p in last.get("pauses") or [] if p.get("start")]
    return {"in": _brief_mark(last["in"]), "out": _brief_mark(last["out"]) if last.get("out") else None, "pauses": pauses}


def crm_person(person: dict) -> dict:
    now = person.get("now") or {}
    state = people_state(person)
    mark = last_mark_of(person)
    since = now.get("since")
    if since and (not mark or str(mark.get("at") or "") < str(since.get("at") or "")):
        # Entro en este mismo minuto: su turno aun no tiene linea de tiempo, pero ya marco.
        mark = {"k": "in", "label": reports_board.MARK_LABEL["in"], "t": since["t"], "d": since["d"], "a": since["a"], "place": "", "s": None, "o": since.get("o") or ""}
    out = {"id": person["id"], "name": person["name"], "role": person.get("role") or "", "state": state,
           "last_mark": mark, "origin": (mark or {}).get("o") or "", "can_finish": state in ("working", "on_break"), "shift": latest_shift(person, since)}
    if now.get("minutes") is not None:
        out["minutes"] = int(now["minutes"])
    if now.get("end"):
        out["end"] = now["end"]
    if since:
        out["since"] = since["t"]
    return out


def sanitize_board(board: dict, place: dict) -> dict:
    """El Board del lider: su operacion con su color y sin documentos ni permisos de edicion."""
    for op in board.get("operations") or []:
        op["color"] = place["accent"]
        for person in op.get("people") or []:
            person.pop("document", None)
    board["scope"] = {"limited": True, "supervisor_no_place": False}
    board["can_manage"] = False
    return board


# ------------------------------------------------------------------ datos
async def available(db: AsyncSession, company_id: Any) -> bool:
    return await work_locations.is_on(db, company_id) and await geo.is_on(db, company_id)


async def places(db: AsyncSession, company_id: Any) -> list[dict]:
    """Operaciones activas de este a oeste. accent: 0 verde agua, 1 ambar (como en el Board)."""
    ordered = reports_board.order_operations([loc for loc in await work_locations.list_locations(db, company_id) if loc["is_active"]])
    return [{**loc, "slug": slug(loc["name"]), "accent": index if index <= 1 else "x", "abbr": us_time.abbr(loc["timezone"])} for index, loc in enumerate(ordered)]


async def supervisors(db: AsyncSession, company_id: Any, place_id: Any) -> list[dict]:
    """Empleados activos con rol Supervisor asignados a la operacion: su lugar de trabajo o la
    lista de supervisores del lugar (la misma regla del Board)."""
    rows = (await db.execute(text("""
        SELECT e.id::text AS id, COALESCE(e.full_name, '') AS name, COALESCE(e.role, '') AS role
        FROM employees e
        WHERE e.company_id = CAST(:c AS uuid) AND lower(COALESCE(e.status, 'active')) IN ('active', 'activo')
          AND (e.work_location_id = CAST(:l AS uuid) OR EXISTS (
                SELECT 1 FROM work_location_supervisors s
                WHERE s.company_id = e.company_id AND s.location_id = CAST(:l AS uuid) AND s.employee_id = e.id))
    """), {"c": str(company_id), "l": str(place_id)})).mappings().all()
    found = [{"id": r["id"], "name": r["name"].strip() or "Colaborador", "role": r["role"]} for r in rows
             if work_locations.role_of(r["role"]) in work_locations.SUPERVISOR_ROLES]
    return sorted(found, key=lambda r: reports_board.sort_key(r["name"]))


async def qualifies(db: AsyncSession, company_id: Any, user: Any, place: dict) -> bool:
    if not is_leader_of(user, place["id"]):
        return False
    employee_id = str(leader_settings(user).get("employee_id"))
    return any(s["id"] == employee_id for s in await supervisors(db, company_id, place["id"]))


async def _person_of(db: AsyncSession, company_id: Any, user: Any) -> dict:
    from app.services import employee_roles

    row = (await db.execute(text("""
        SELECT COALESCE(full_name, '') AS name, COALESCE(role, '') AS role FROM employees
        WHERE company_id = CAST(:c AS uuid) AND id = CAST(:e AS uuid)
    """), {"c": str(company_id), "e": str(leader_settings(user).get("employee_id"))})).mappings().first()
    config = await employee_roles.load_config(db, str(company_id))
    role = (row or {}).get("role") or "Supervisor"
    return {"name": ((row or {}).get("name") or "").strip() or str(getattr(user, "full_name", "") or ""),
            "role": employee_roles.display(config, role) if config else role}


def _local(place: dict, now: datetime) -> datetime:
    return now.astimezone(us_time.zone(place["timezone"]))


async def _board(db: AsyncSession, company_id: Any, place: dict, start: date, end: date, now: datetime) -> tuple[dict, dict]:
    board = sanitize_board(await reports_board.build(db, company_id, start, end, places=[place["id"]], now=now), place)
    return board, (board["operations"] or [{}])[0]


async def inicio(db: AsyncSession, company_id: Any, user: Any, place: dict, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = _local(place, now).date()
    start, end = week_of(today, (await us_payroll.rules(db, str(company_id))).get("week_start_day"))
    board, op = await _board(db, company_id, place, start, end, now)
    people = op.get("people") or []
    notes_today = sum(1 for n in op.get("notes") or [] if n.get("d") == today.isoformat())
    return {
        "ok": True, "company": board["company"]["name"], "me": await _person_of(db, company_id, user), "operation": _operation_out(place, now),
        "crm": count_states(people),
        "reports": {"hours_minutes": int((op.get("figures") or {}).get("connected") or 0), "alerts": len(op.get("alerts") or []), "notes_today": notes_today,
                    "notes": int((op.get("figures") or {}).get("notes") or 0), "week": {"start": start.isoformat(), "end": end.isoformat()}},
    }


async def crm(db: AsyncSession, company_id: Any, place: dict, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = _local(place, now).date()
    _, op = await _board(db, company_id, place, today - timedelta(days=CRM_DAYS - 1), today, now)
    people = op.get("people") or []
    return {"ok": True, "operation": _operation_out(place, now), "counts": count_states(people), "people": [crm_person(p) for p in people],
            "limit_hours": await reports_board._policy_hours(db, company_id)}


async def attendance_pdf(db: AsyncSession, company_id: Any, user: Any, place: dict, lang: str = "es", now: Optional[datetime] = None) -> bytes:
    """PDF "Lista de asistencia" de SU operacion, con los mismos datos de CRM Campo."""
    from app.services import lider_pdf

    now = now or datetime.now(timezone.utc)
    data = await crm(db, company_id, place, now)
    name = (await db.execute(text("SELECT COALESCE(name, '') FROM companies WHERE id = CAST(:c AS uuid)"), {"c": str(company_id)})).scalar() or ""
    me = await _person_of(db, company_id, user)
    logo = await lider_pdf.company_logo(db, company_id)
    return lider_pdf.build_attendance_pdf(data, company=name, leader=me["name"], logo=logo, now=now, limit_hours=data["limit_hours"], lang=lang)


async def report_pdf(db: AsyncSession, company_id: Any, user: Any, place: dict, start: date, end: date, lang: str = "es", now: Optional[datetime] = None) -> bytes:
    from app.services import lider_pdf

    now = now or datetime.now(timezone.utc)
    board = await reportes(db, company_id, place, start, end, now)
    me = await _person_of(db, company_id, user)
    logo = await lider_pdf.company_logo(db, company_id)
    return lider_pdf.build_report_pdf(board, logo=logo, now=now, leader=me["name"], lang=lang)


async def reportes(db: AsyncSession, company_id: Any, place: dict, start: date, end: date, now: Optional[datetime] = None) -> dict:
    board, _ = await _board(db, company_id, place, start, end, now or datetime.now(timezone.utc))
    return board


async def reportes_live(db: AsyncSession, company_id: Any, place: dict) -> dict:
    return await reports_board.live_block(db, company_id, places=[place["id"]])


def _operation_out(place: dict, now: datetime) -> dict:
    local = _local(place, now)
    return {"id": place["id"], "name": place["name"], "code": place.get("code"), "timezone": place["timezone"], "abbr": us_time.abbr(place["timezone"], now),
            "accent": place["accent"], "slug": place["slug"], "local_time": local.strftime("%H:%M"), "local_date": local.date().isoformat()}


async def entry_page(db: AsyncSession, company_id: Any, wanted: Any) -> dict:
    """Lo que necesita la pantalla de ingreso, incrustado en el HTML (sin endpoint publico): el
    nombre de la operacion del enlace, su color y la marca publica. Sin datos de personas."""
    from app.web import brand_inject
    from app.services import brand_theme

    if not await available(db, company_id):
        return {"ok": False}
    place = resolve_place(await places(db, company_id), wanted)
    if not place:
        return {"ok": False}
    try:
        tokens = await brand_inject.published_theme(db, company_id)
        if tokens:
            branding = brand_theme.branding_for_panels(tokens, str(company_id))
        else:
            from app.api.v1.endpoints.companies import _get_company_or_404, _read_company_branding

            branding = _read_company_branding(await _get_company_or_404(db, company_id))
        brand = {k: branding.get(k) for k in brand_inject.BRAND_KEYS if branding.get(k) not in (None, "")}
    except Exception:  # sin marca, el panel entra igual con los colores por defecto
        await db.rollback()
        brand = {}
    return {"ok": True, "name": place["name"], "slug": place["slug"], "accent": place["accent"], "abbr": place["abbr"], "timezone": place["timezone"], "brand": brand}
