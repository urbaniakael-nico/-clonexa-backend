"""Perimetros (geocercas) y supervisores por lugar de trabajo (interruptor reports_board).

Nada se guarda solo: los perimetros los carga el dueno en Administrar lugares. Con un
perimetro guardado, las marcas NUEVAS del bot se miden dentro / fuera; las viejas solo con
"Recalcular marcas viejas", que toca payload_json (estado del perimetro) y nunca la hora
ni las coordenadas, asi que no cambia ninguna cifra de horas. Toda consulta filtra por
company_id.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SWITCH = "reports_board"
MODULE = "reports"
GEO_SOURCE = "place"  # esta marca se midio con los perimetros de su lugar
DEFAULT_RADIUS_M = 300
MIN_RADIUS_M = 20
MAX_RADIUS_M = 20000
MAX_PERIMETERS = 10
MAX_SUPERVISORS = 20
SUGGEST_DAYS = 7
NEAR_OT_KEY = "reports_board_near_ot_hours"
DEFAULT_NEAR_OT_HOURS = 36.0
LABELS = {"inside": "En perímetro", "outside": "Fuera de perímetro"}


class Invalid(ValueError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ------------------------------------------------------------------ reglas puras
def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia en metros sobre la Tierra (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000.0 * math.asin(min(1.0, math.sqrt(a)))


def classify(lat: float, lng: float, perimeters: Iterable[dict]) -> dict:
    """Marca contra los perimetros de su lugar. Dentro de cualquiera = En perimetro."""
    best = None
    for p in perimeters:
        d = distance_m(lat, lng, float(p["latitude"]), float(p["longitude"]))
        if d <= float(p["radius_m"]) and (best is None or d < best[0]):
            best = (d, p)
    if best:
        return {"gps_status": "inside", "gps_status_label": LABELS["inside"], "matched_perimeter_id": str(best[1].get("id") or "") or None,
                "matched_perimeter_name": best[1].get("name"), "matched_perimeter_slot": None, "geo_source": GEO_SOURCE}
    return {"gps_status": "outside", "gps_status_label": LABELS["outside"], "matched_perimeter_id": None,
            "matched_perimeter_name": None, "matched_perimeter_slot": None, "geo_source": GEO_SOURCE}


def suggest_center(points: list[tuple[float, float]]) -> dict | None:
    """Punto medio de las marcaciones: la mediana de latitud y de longitud, para que una
    marcacion suelta lejos (desde la casa, GPS malo) no mueva el centro. Da tambien a que
    distancia quedo el 90 % de las marcaciones, para elegir el radio."""
    if not points:
        return None
    lat, lng = median(p[0] for p in points), median(p[1] for p in points)
    gaps = sorted(distance_m(lat, lng, a, b) for a, b in points)
    return {"latitude": round(lat, 7), "longitude": round(lng, 7), "marks": len(points),
            "p90_m": int(round(gaps[min(len(gaps) - 1, math.ceil(len(gaps) * 0.9) - 1)]))}


def validate_place(body: Any, employee_ids: set[str]) -> tuple[list[dict], list[str]]:
    """Cuerpo de PUT /places/{id}: perimetros y supervisores, limpios."""
    body = body if isinstance(body, dict) else {}
    raw = body.get("perimeters")
    if not isinstance(raw, list):
        raise Invalid("Envía la lista de perímetros.")
    if len(raw) > MAX_PERIMETERS:
        raise Invalid(f"Máximo {MAX_PERIMETERS} perímetros por lugar.")
    out = []
    names: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise Invalid("Perímetro no válido.")
        name = " ".join(str(item.get("name") or "").split())[:80] or f"Perímetro {i + 1}"
        if name.lower() in names:
            raise Invalid(f"El perímetro «{name}» está repetido.")
        names.add(name.lower())
        try:
            lat, lng = float(item.get("latitude")), float(item.get("longitude"))
        except (TypeError, ValueError):
            raise Invalid(f"«{name}»: escribe la latitud y la longitud.") from None
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            raise Invalid(f"«{name}»: la latitud va de -90 a 90 y la longitud de -180 a 180.")
        radius = item.get("radius_m")
        try:
            radius = int(float(radius)) if radius not in (None, "") else DEFAULT_RADIUS_M
        except (TypeError, ValueError):
            raise Invalid(f"«{name}»: el radio debe ser un número de metros.") from None
        if not (MIN_RADIUS_M <= radius <= MAX_RADIUS_M):
            raise Invalid(f"«{name}»: el radio va de {MIN_RADIUS_M} a {MAX_RADIUS_M} metros.")
        out.append({"name": name, "latitude": round(lat, 7), "longitude": round(lng, 7), "radius_m": radius})
    supervisors = body.get("supervisors")
    if not isinstance(supervisors, list):
        raise Invalid("Envía la lista de supervisores.")
    ids = sorted({str(s).strip() for s in supervisors if str(s or "").strip()})
    if len(ids) > MAX_SUPERVISORS:
        raise Invalid(f"Máximo {MAX_SUPERVISORS} supervisores por lugar.")
    if any(i not in employee_ids for i in ids):
        raise Invalid("Algún supervisor no es empleado activo de esta empresa.")
    return out, ids


# ------------------------------------------------------------------ interruptor
def _settings(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


async def module_settings(db: AsyncSession, company_id: Any) -> dict | None:
    row = (await db.execute(text("""
        SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:c AS uuid) AND m.code = :m AND cm.enabled IS TRUE LIMIT 1
    """), {"c": str(company_id), "m": MODULE})).first()
    return _settings(row[0]) if row else None


async def is_on(db: AsyncSession, company_id: Any) -> bool:
    return (await module_settings(db, company_id) or {}).get(SWITCH) is True


def near_ot_minutes(settings: dict | None) -> int:
    try:
        hours = float((settings or {}).get(NEAR_OT_KEY))
        if 1 <= hours <= 168:
            return int(round(hours * 60))
    except (TypeError, ValueError):
        pass
    return int(DEFAULT_NEAR_OT_HOURS * 60)


async def save_near_ot(db: AsyncSession, company_id: Any, hours: Any) -> float:
    try:
        value = float(hours)
    except (TypeError, ValueError):
        raise Invalid("Escribe las horas de la alerta de overtime.") from None
    if not (1 <= value <= 168):
        raise Invalid("La alerta de overtime va de 1 a 168 horas.")
    await db.execute(text("""
        UPDATE company_modules SET settings = COALESCE(settings, '{}'::jsonb) || jsonb_build_object(CAST(:k AS text), CAST(:v AS numeric))
        WHERE company_id = CAST(:c AS uuid) AND module_id = (SELECT id FROM modules WHERE code = :m)
    """), {"k": NEAR_OT_KEY, "v": value, "c": str(company_id), "m": MODULE})
    await db.commit()
    return value


# ------------------------------------------------------------------ datos
async def perimeters_by_place(db: AsyncSession, company_id: Any) -> dict[str, list[dict]]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, location_id::text AS location_id, name, latitude, longitude, radius_m, created_at
        FROM work_location_perimeters WHERE company_id = CAST(:c AS uuid) ORDER BY created_at, name
    """), {"c": str(company_id)})).mappings().all()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["location_id"], []).append({"id": r["id"], "name": r["name"], "latitude": float(r["latitude"]),
                                                     "longitude": float(r["longitude"]), "radius_m": int(r["radius_m"])})
    return out


async def supervisors_by_place(db: AsyncSession, company_id: Any) -> dict[str, list[dict]]:
    rows = (await db.execute(text("""
        SELECT s.location_id::text AS location_id, e.id::text AS employee_id, COALESCE(e.full_name, '') AS name
        FROM work_location_supervisors s
        JOIN employees e ON e.id = s.employee_id AND e.company_id = s.company_id
        WHERE s.company_id = CAST(:c AS uuid)
        ORDER BY lower(COALESCE(e.full_name, ''))
    """), {"c": str(company_id)})).mappings().all()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["location_id"], []).append({"employee_id": r["employee_id"], "name": r["name"].strip()})
    return out


async def _place_or_invalid(db: AsyncSession, company_id: Any, location_id: Any) -> dict:
    row = (await db.execute(text("""
        SELECT id::text AS id, name FROM work_locations WHERE id = CAST(:l AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"l": str(location_id), "c": str(company_id)})).mappings().first()
    if not row:
        raise Invalid("Ese lugar no es de esta empresa.")
    return dict(row)


async def active_employees(db: AsyncSession, company_id: Any) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, COALESCE(full_name, '') AS name, COALESCE(role, '') AS role, work_location_id::text AS work_location_id
        FROM employees
        WHERE company_id = CAST(:c AS uuid) AND lower(COALESCE(status, 'active')) IN ('active', 'activo')
        ORDER BY lower(COALESCE(full_name, ''))
    """), {"c": str(company_id)})).mappings().all()
    return [{**dict(r), "name": r["name"].strip()} for r in rows]


async def save_place(db: AsyncSession, company_id: Any, location_id: Any, body: Any, actor: str) -> dict:
    """Deja el lugar con EXACTAMENTE los perimetros y supervisores enviados."""
    await _place_or_invalid(db, company_id, location_id)
    employees = await active_employees(db, company_id)
    perimeters, supervisors = validate_place(body, {e["id"] for e in employees})
    params = {"c": str(company_id), "l": str(location_id), "by": str(actor or "")[:200] or None}
    await db.execute(text("DELETE FROM work_location_perimeters WHERE company_id = CAST(:c AS uuid) AND location_id = CAST(:l AS uuid)"), params)
    for p in perimeters:
        await db.execute(text("""
            INSERT INTO work_location_perimeters (company_id, location_id, name, latitude, longitude, radius_m, created_by)
            VALUES (CAST(:c AS uuid), CAST(:l AS uuid), :n, :lat, :lng, :r, :by)
        """), {**params, "n": p["name"], "lat": p["latitude"], "lng": p["longitude"], "r": p["radius_m"]})
    await db.execute(text("DELETE FROM work_location_supervisors WHERE company_id = CAST(:c AS uuid) AND location_id = CAST(:l AS uuid)"), params)
    for eid in supervisors:
        await db.execute(text("""
            INSERT INTO work_location_supervisors (company_id, location_id, employee_id, created_by)
            VALUES (CAST(:c AS uuid), CAST(:l AS uuid), CAST(:e AS uuid), :by)
        """), {**params, "e": eid})
    await db.commit()
    return {"perimeters": (await perimeters_by_place(db, company_id)).get(str(location_id), []),
            "supervisors": (await supervisors_by_place(db, company_id)).get(str(location_id), [])}


async def supervisor_places(db: AsyncSession, company_id: Any, email: Any, full_name: Any) -> list[str]:
    """Lugares de un usuario supervisor del portal. El usuario no guarda su empleado: se une
    por correo y, si no hay, por nombre, solo dentro de la empresa. Vale el lugar en el que
    figura como supervisor y su lugar de trabajo. Vacio = sin lugar."""
    rows = (await db.execute(text("""
        SELECT e.id::text AS id, e.work_location_id::text AS place, lower(trim(COALESCE(e.email, ''))) AS email, lower(trim(COALESCE(e.full_name, ''))) AS name
        FROM employees e WHERE e.company_id = CAST(:c AS uuid)
          AND (lower(trim(COALESCE(e.email, ''))) = :mail OR lower(trim(COALESCE(e.full_name, ''))) = :name)
    """), {"c": str(company_id), "mail": str(email or "").strip().lower() or "\0", "name": str(full_name or "").strip().lower() or "\0"})).mappings().all()
    mail = str(email or "").strip().lower()
    mine = [r for r in rows if mail and r["email"] == mail] or list(rows)
    places = {r["place"] for r in mine if r["place"]}
    if mine:
        listed = (await db.execute(text("""
            SELECT location_id::text FROM work_location_supervisors
            WHERE company_id = CAST(:c AS uuid) AND employee_id::text = ANY(:ids)
        """), {"c": str(company_id), "ids": [r["id"] for r in mine]})).scalars().all()
        places |= set(listed)
    return sorted(places)


# ------------------------------------------------------------------ marcas
async def stamp_or_none(db: AsyncSession, company_id: Any, employee_id: Any, latitude: float, longitude: float) -> dict | None:
    """Para el bot: el estado de una marca nueva segun los perimetros del lugar de la
    persona. None si el interruptor esta apagado o el lugar no tiene perimetro (el bot sigue
    como siempre). Nunca rompe una marcacion."""
    try:
        async with db.begin_nested():
            if not await is_on(db, company_id):
                return None
            rows = (await db.execute(text("""
                SELECT p.id::text AS id, p.name, p.latitude, p.longitude, p.radius_m
                FROM employees e JOIN work_location_perimeters p ON p.location_id = e.work_location_id AND p.company_id = e.company_id
                WHERE e.id = CAST(:e AS uuid) AND e.company_id = CAST(:c AS uuid)
            """), {"e": str(employee_id), "c": str(company_id)})).mappings().all()
        return classify(latitude, longitude, [dict(r) for r in rows]) if rows else None
    except Exception:
        return None


async def _punches(db: AsyncSession, company_id: Any, since: datetime | None = None, kinds: tuple = ()) -> list[dict]:
    from app.services import us_payroll

    cid = str(company_id)
    since_sql = "AND COALESCE(ev.occurred_at, ev.created_at) >= :since" if since else ""
    rows = (await db.execute(text(f"""
        SELECT ev.id::text AS id, ev.employee_id::text AS employee_id, ev.event_type, ev.event_label, ev.status_after, ev.detail,
               ev.payload_json, ev.latitude, ev.longitude, COALESCE(ev.occurred_at, ev.created_at) AS occurred_at
        FROM workforce_attendance_events ev
        WHERE ev.company_id = CAST(:c AS uuid) AND ev.employee_id IS NOT NULL AND ev.event_type <> 'gps_location' {since_sql}
    """), {"c": cid, **({"since": since} if since else {})})).mappings().all()
    events = []
    for r in rows:
        ev = dict(r)
        ev["occurred_at"] = us_payroll._dt(ev["occurred_at"])
        ev["kind"] = us_payroll._kind(ev)
        if ev["kind"] in (kinds or us_payroll.PUNCHES) and ev["occurred_at"]:
            events.append(ev)
    nearest = await us_payroll.nearest_gps(db, cid, events)
    for ev in events:
        loc = us_payroll._location(ev, nearest.get(ev["id"]))
        ev["lat"], ev["lng"] = loc["lat"], loc["lng"]
    return events


async def suggestion(db: AsyncSession, company_id: Any, location_id: Any, now: datetime | None = None) -> dict:
    """Centro sugerido con las marcaciones de ENTRADA del lugar en los ultimos 7 dias. Solo lo
    calcula: no guarda nada; se guarda si el dueno lo confirma con "Guardar"."""
    await _place_or_invalid(db, company_id, location_id)
    now = now or datetime.now(timezone.utc)
    people = (await db.execute(text("""
        SELECT id::text FROM employees WHERE company_id = CAST(:c AS uuid) AND work_location_id = CAST(:l AS uuid)
    """), {"c": str(company_id), "l": str(location_id)})).scalars().all()
    ids = set(people)
    events = await _punches(db, company_id, since=now - timedelta(days=SUGGEST_DAYS), kinds=("check_in",))
    points = [(ev["lat"], ev["lng"]) for ev in events if ev["employee_id"] in ids and ev["lat"] is not None and ev["lng"] is not None]
    center = suggest_center(points)
    return {"days": SUGGEST_DAYS, "suggestion": center, "saved": False}


async def recalculate(db: AsyncSession, company_id: Any, location_id: Any) -> dict:
    """Vuelve a medir las marcas del lugar con sus perimetros de hoy. Escribe SOLO el estado
    en payload_json: la hora y las coordenadas no se tocan y las horas no cambian. Vale el
    lugar donde estaba la persona ese dia (traslados)."""
    from app.services import us_payroll, work_locations

    await _place_or_invalid(db, company_id, location_id)
    perimeters = (await perimeters_by_place(db, company_id)).get(str(location_id), [])
    if not perimeters:
        raise Invalid("Primero guarda al menos un perímetro en este lugar.")
    cid = str(company_id)
    current = await work_locations.assignments(db, cid)
    changes: dict[str, list[dict]] = {}
    for r in (await db.execute(text("""
        SELECT employee_id::text AS employee_id, from_location_id::text AS from_location_id, to_location_id::text AS to_location_id, changed_at
        FROM work_location_changes WHERE company_id = CAST(:c AS uuid)
    """), {"c": cid})).mappings().all():
        changes.setdefault(r["employee_id"], []).append({**dict(r), "changed_at": us_payroll._dt(r["changed_at"])})
    ids, patches = [], []
    counts = {"inside": 0, "outside": 0, "no_location": 0}
    for ev in await _punches(db, cid):
        if work_locations.location_on(changes.get(ev["employee_id"], []), current.get(ev["employee_id"]), ev["occurred_at"]) != str(location_id):
            continue
        if ev["lat"] is None or ev["lng"] is None:
            counts["no_location"] += 1
            continue
        result = classify(ev["lat"], ev["lng"], perimeters)
        counts[result["gps_status"]] += 1
        patch = {k: result[k] for k in ("gps_status", "gps_status_label", "matched_perimeter_id", "matched_perimeter_name", "geo_source")}
        punch = us_payroll._json(ev.get("payload_json")).get("punch_location")
        if isinstance(punch, dict):
            patch["punch_location"] = {**punch, **patch}
        ids.append(ev["id"])
        patches.append(json.dumps(patch))
    if ids:
        await db.execute(text("""
            UPDATE workforce_attendance_events ev SET payload_json = COALESCE(ev.payload_json, '{}'::jsonb) || CAST(p.patch AS jsonb)
            FROM (SELECT unnest(CAST(:ids AS text[])) AS id, unnest(CAST(:patches AS text[])) AS patch) p
            WHERE ev.id::text = p.id AND ev.company_id = CAST(:c AS uuid)
        """), {"ids": ids, "patches": patches, "c": cid})
    await db.commit()
    return {"updated": len(ids), **counts}
