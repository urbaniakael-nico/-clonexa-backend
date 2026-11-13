"""Oficina 3D · pisos aprobados (025m): copia viva de Velvet (taller), Asadero (restaurante), VOLTAGE (campo)
y del piso de Clonexa. Interno de Clonexa (solo Admin V2 / v2+): ninguna empresa cliente ve nada nuevo.

REGLA DE ORO: todo sale de datos reales de Clonexa (o de n8n, lo que ya usa la oficina). Si un dato no existe,
el campo va en None y la pantalla muestra "—" (nunca un numero de ejemplo).
- Nada de dinero en pisos de clientes (oficina_vivo.without_money al final). En Clonexa, Tesoreria solo el
  ESTADO de cobro de cada empresa (al dia / vence / vencido) desde Facturacion, sin montos.
- Privacidad del personal: nombre + inicial y cargo, o solo cargo (la del piso).
- Toda consulta de una empresa filtra por su company_id.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

from app.services import oficina as of
from app.services import oficina_data as od
from app.services import oficina_vivo as ov

log = logging.getLogger("clonexa.oficina")

NO = None
MACHINES_MIN, MACHINES_MAX = 6, 12
CAMPO_VISIBLE = 5
KITCHEN_MAX, DELIVERY_MAX = 6, 6
HEAVY_TTL = 30.0
DAYS = ("L", "M", "M", "J", "V", "S", "D")
_HEAVY: dict[str, tuple[float, Any]] = {}


def reset() -> None:
    _HEAVY.clear()


async def _heavy(key: str, fn):
    """Consultas pesadas (insights de produccion, facturacion) a lo sumo cada 30 s."""
    hit = _HEAVY.get(key)
    if hit and time.monotonic() - hit[0] < HEAVY_TTL:
        return hit[1]
    value = await fn()
    _HEAVY[key] = (time.monotonic(), value)
    return value


def person_key(employee_id: Any) -> str:
    return hashlib.sha256(f"{employee_id}".encode()).hexdigest()[:12]


def person_label(name: Any, role: Any, privacy: str) -> str:
    short, r = of.short_name(name), of.role_label(role)
    return r if privacy == "cargo" or not short else f"{short} · {r}"


def first_name(name: Any) -> str:
    """Solo para elegir el genero por defecto en el navegador (nunca se muestra con privacidad 'cargo')."""
    parts = str(name or "").strip().split()
    return parts[0].capitalize() if parts else ""


def _finish(snap: dict) -> dict:
    snap = ov.without_money(snap)
    snap["rev"] = ov.rev(snap)
    return snap


# ================================================================== VELVET · taller
def machines_for(active_people: Optional[int]) -> int:
    """Una maquina por cada persona que puede trabajar en produccion: minimo 6, maximo 12."""
    return max(MACHINES_MIN, min(MACHINES_MAX, int(active_people or 0)))


def paused_minutes(paused_since: Any, now: datetime) -> Optional[int]:
    at = of.parse_dt(paused_since)
    return int(max(0, (now - at).total_seconds()) // 60) if at else None


def week_series(rows: Optional[list[dict]], today: date) -> Optional[list[dict]]:
    """Prendas cerradas por dia de esta semana (lunes a domingo). None = sin datos (no ceros inventados);
    los dias que aun no llegan van en None."""
    if rows is None:
        return None
    monday = today - timedelta(days=today.weekday())
    by = {r["day"]: int(r["n"] or 0) for r in rows if r.get("day")}
    return [{"d": DAYS[i], "n": by.get(monday + timedelta(days=i), 0) if monday + timedelta(days=i) <= today else None} for i in range(7)]


def taller_board(lot: Optional[dict], people: list[dict], hours: str, week: Optional[list[dict]], sent: Optional[dict]) -> dict:
    """Tablero de produccion (funcion pura). Lo que Clonexa no tiene queda en None."""
    working = sum(1 for p in people if p["status"] == "working")
    paused = sum(1 for p in people if p["status"] == "paused")
    out = {"lot": None, "made": None, "meta": None, "percent": None, "day": None, "on_shift": working, "paused": paused,
           "hours": hours, "week": week, "week_sum": sum(d["n"] or 0 for d in week) if week else None,
           "sent": None, "to_send": None, "next_send": None}
    if lot:
        meta, made = int(lot.get("meta") or 0), int(lot.get("closed") or 0)
        out.update(lot=lot.get("name") or None, made=made, meta=meta or None,
                   percent=round(made * 100 / meta) if meta else None, day=lot.get("days_open"))
    if sent and sent.get("status") == "ok":
        out.update(sent=sent.get("value"), to_send=sent.get("to_send"))
    return out


def taller_people(team: Optional[dict], privacy: str, now: datetime) -> list[dict]:
    out = []
    for p in (team or {}).get("live") or []:
        status = "paused" if p.get("status") == "on_break" else "working"
        out.append({"key": person_key(p["employee_id"]), "label": person_label(p.get("name"), p.get("role"), privacy),
                    "first": first_name(p.get("name")) if privacy != "cargo" else "", "status": status,
                    "uniform": of.uniform_for(p.get("role"), "taller"),   # la misma plantilla del editor que en el edificio
                    "reference": (p.get("reference_name") or None) if status == "working" else None,
                    "paused_min": paused_minutes(p.get("paused_since"), now) if status == "paused" else None})
    return out


async def live_taller(r: od.Reader, c: dict, now: datetime, privacy: str) -> dict:
    from app.services import crm_lab

    cid = c["id"]
    tz = od._zone(c.get("timezone"))
    today = now.astimezone(tz).date()
    team = None
    if await r.has("employees") and await r.has("workforce_attendance_status"):
        try:
            team = await crm_lab.team(r.db, cid, now)
        except Exception as error:
            log.warning("oficina: equipo del taller sin datos (%s)", type(error).__name__)
            await r.db.rollback()
    people = taller_people(team, privacy, now)

    async def insights():
        from app.services import production_v2

        try:
            return await production_v2.insights(r.db, cid, today - timedelta(days=today.weekday()), today, today)
        except Exception as error:
            log.warning("oficina: produccion sin datos (%s)", type(error).__name__)
            await r.db.rollback()
            return None
    ins = await _heavy("ins:" + cid, insights) if await r.has("product_references") else None
    lots = (ins or {}).get("lots_in_process") or []
    lot = lots[0] if lots else None
    week_rows = await r.rows("""
        SELECT (closed_at AT TIME ZONE CAST(:tz AS text))::date AS day, COALESCE(SUM(quantity_finished), 0) AS n
        FROM reference_production_closures WHERE company_id = :c AND closed_at >= :s GROUP BY 1
    """, {"c": cid, "tz": tz.key, "s": datetime(today.year, today.month, today.day, tzinfo=tz) - timedelta(days=today.weekday())},
        tables=("reference_production_closures",))
    shifts = await od.open_shifts(r, cid, now)
    kpis, _lines = await od.taller_kpis(r, c, now, shifts)
    hours = dict(kpis).get("Horas del día", od.NO_DATA)
    board = taller_board(lot, people, hours if hours != od.NO_DATA else None, week_series(week_rows, today),
                         ((ins or {}).get("kpis") or {}).get("sent"))
    return _finish({"ok": True, "company_id": cid, "template": "taller", "privacy": privacy,
                    "machines": machines_for(len((team or {}).get("people") or []) or len(people)),
                    "people": people, "board": board, "kpis": kpis, "brand": await ov.brand(r.db, cid, c.get("settings")),
                    "known": {"team": team is not None, "production": ins is not None, "week": week_rows is not None}})


# ================================================================== ASADERO · restaurante
def delivery_state(status: str, meta: Optional[dict]) -> str:
    """Domicilio: en cocina (pendiente/alistando), en camino (salio con el domiciliario), entregado (cerrado)."""
    st = str(status or "").lower()
    d = (meta or {}).get("delivery") if isinstance(meta, dict) else None
    if st in ("cerrado", "pagado"):
        return "entregado"
    if isinstance(d, dict) and d.get("dispatched_at"):
        return "camino"
    if st == "entregado":
        return "listo"
    return "cocina"


def minutes_since(at: Any, now: datetime) -> Optional[int]:
    t = of.parse_dt(at)
    return int(max(0, (now - t).total_seconds()) // 60) if t else None


async def live_restaurante(r: od.Reader, c: dict, now: datetime, privacy: str) -> dict:
    from app.services import carta_links

    cid = c["id"]
    tz = od._zone(c.get("timezone"))
    try:
        tables = await carta_links.mesa_labels(r.db, cid)
    except Exception as error:
        log.warning("oficina: mesas sin datos (%s)", type(error).__name__)
        await r.db.rollback()
        tables = None
    start, end, _label = of.jornada(now, tz, c.get("business_day"))
    access = await r.rows("""
        SELECT a.table_key, COALESCE(a.table_number, '') AS table_number, a.activated_at,
               (SELECT COUNT(*) FROM hospitality_table_guests g WHERE g.company_id = a.company_id AND g.access_id = a.id) AS guests
        FROM hospitality_table_access a
        WHERE a.company_id = CAST(:c AS uuid) AND lower(COALESCE(a.status, '')) = 'active' AND (a.expires_at IS NULL OR a.expires_at > :n)
    """, {"c": cid, "n": now}, tables=("hospitality_table_access", "hospitality_table_guests"))
    rows = await r.rows(f"""
        SELECT o.id::text AS id, COALESCE(o.table_key, '') AS table_key, COALESCE(o.table_number, '') AS table_number,
               lower(o.status) AS status, lower(COALESCE(o.order_type, 'table')) AS order_type, o.created_at,
               COALESCE(o.updated_at, o.created_at) AS updated_at, {ov.QTY_SQL} AS items,
               COALESCE(o.metadata->'delivery'->>'barrio', '') AS barrio,
               (o.metadata->'delivery'->>'dispatched_at') AS dispatched_at
        FROM hospitality_orders o
        WHERE o.company_id = CAST(:c AS uuid) AND o.created_at >= LEAST(:s, CAST(:recent AS timestamptz)) AND o.cancelled_at IS NULL
          AND (o.archived_at IS NULL OR lower(COALESCE(o.order_type, 'table')) = 'domicilio')
        ORDER BY o.created_at
    """, {"c": cid, "s": start, "recent": now - timedelta(hours=12)}, tables=("hospitality_orders",))
    labels = tables or []
    orders, kitchen, deliveries = [], [], []
    for o in rows or []:
        if o["status"] in od.CANCELLED:
            continue
        items = max(1, int(o["items"] or 0))
        if o["order_type"] == "domicilio":
            st = delivery_state(o["status"], {"delivery": {"dispatched_at": o.get("dispatched_at")}})
            name = ov._short(o["table_number"] or "Domicilio", 30)
            if of.parse_dt(o["created_at"]) and of.parse_dt(o["created_at"]) >= start:
                deliveries.append({"id": ov._hid(o["id"]), "label": name, "barrio": ov._short(o.get("barrio"), 40) or None, "state": st,
                                   "at": of.iso(o["created_at"])})
            if st == "cocina":
                kitchen.append({"label": name, "detail": f"{items} {'producto' if items == 1 else 'productos'}", "minutes": minutes_since(o["created_at"], now),
                                "kind": "domicilio"})
            continue
        if o["status"] not in ov.ORDER_STATE:
            continue
        label = ov.table_label(o["table_number"], o["table_key"], labels)
        state = ov.ORDER_STATE[o["status"]]
        orders.append({"id": ov._hid(o["id"]), "table": label, "state": state, "items": items, "at": of.iso(o["created_at"]),
                       "updated_at": of.iso(o["updated_at"])})
        if state in ("nuevo", "preparando"):
            kitchen.append({"label": label, "detail": f"{items} {'producto' if items == 1 else 'productos'}", "minutes": minutes_since(o["created_at"], now),
                            "kind": "mesa"})
    open_tables: dict[str, dict] = {}
    for a in access or []:
        lb = ov.table_label(a["table_number"], a["table_key"], labels)
        open_tables[lb] = {"since": of.iso(a["activated_at"]), "guests": int(a["guests"] or 0) or None}
    plates: dict[str, int] = {}
    for o in orders:
        plates[o["table"]] = plates.get(o["table"], 0) + 1
        open_tables.setdefault(o["table"], {"since": o["at"], "guests": None})
    all_tables = labels + sorted(t for t in open_tables if t not in labels)
    kitchen.sort(key=lambda k: -(k["minutes"] or 0))
    deliveries.sort(key=lambda d: d["at"] or "", reverse=True)
    shifts = await od.open_shifts(r, cid, now)
    staff = of.staff_out(shifts or [], "restaurante", privacy) if shifts is not None else {"total": None, "visible": [], "extra": 0}
    kpis, _lines = await od.restaurante_kpis(r, c, now, shifts)
    return _finish({"ok": True, "company_id": cid, "template": "restaurante", "privacy": privacy,
                    "tables": [{"label": t, "open": t in open_tables, "plates": plates.get(t, 0), **(open_tables.get(t) or {"since": None, "guests": None})}
                               for t in all_tables],
                    "orders": orders, "kitchen": kitchen[:KITCHEN_MAX], "kitchen_count": len(kitchen),
                    "deliveries": deliveries[:DELIVERY_MAX], "on_the_way": [d for d in deliveries if d["state"] == "camino"][:2],
                    "staff": {"count": staff.get("total"), "extra": staff.get("extra", 0),
                              "people": [{**{k: p[k] for k in ("key", "label", "role", "uniform", "paused")}, "first": ""} for p in staff["visible"]]},
                    "kpis": kpis, "brand": await ov.brand(r.db, cid, c.get("settings")),
                    "known": {"tables": tables is not None, "orders": rows is not None, "access": access is not None, "staff": shifts is not None}})


# ================================================================== VOLTAGE · campo
def campo_role(role: Any) -> str:
    r = of.fold(role)
    if re.search(r"supervis|lider|jefe|foreman", r):
        return "supervisor"
    if re.search(r"almac|bodeg|warehouse|material", r):
        return "almacen"
    return "tecnico"


def cut_out(row: Optional[dict], tz) -> Optional[dict]:
    """Ultimo corte de entrada/salida enviado al grupo (historial de avisos de WhatsApp)."""
    if not row:
        return None
    at = of.parse_dt(row.get("at"))
    st = str(row.get("status") or "")
    return {"kind": "entrada" if row.get("kind") == "checkin" else "salida", "at": at.astimezone(tz).strftime("%H:%M") if at else None,
            "status": "enviado" if st == "sent" else "falló" if st in ("failed", "error") else "pendiente"}


def campo_ops(ops: list[dict], shifts: list[dict], outside: set[str], plan: dict[str, tuple[Optional[int], Optional[int]]],
              cuts: dict[str, Optional[dict]], privacy: str) -> list[dict]:
    """Operaciones con su gente en turno (maximo 5 visibles + "+N"), fuera de perimetro y tablero (funcion pura)."""
    names = {o["id"]: o for o in ops}
    groups: dict[str, list[dict]] = {o["id"]: [] for o in ops}
    for s in shifts:
        lid = s.get("work_location_id") or ""
        if lid not in groups:
            lid = "sin_lugar"
            groups.setdefault(lid, [])
        groups[lid].append({"key": person_key(s["employee_id"]), "label": person_label(s.get("employee_name"), s.get("employee_role"), privacy),
                            "first": first_name(s.get("employee_name")) if privacy != "cargo" else "",
                            "role": campo_role(s.get("employee_role")), "paused": str(s.get("status")) == "on_break",
                            "outside": person_key(s["employee_id"]) in outside})
    out = []
    for lid, people in groups.items():
        if lid == "sin_lugar" and not people:
            continue
        o = names.get(lid) or {"name": "Sin lugar asignado", "timezone": None}
        people.sort(key=lambda p: (p["role"] == "tecnico", not p["outside"]))   # supervisor, almacen y fuera de perimetro primero
        scheduled, missing = plan.get(lid, (None, None))
        out.append({"id": lid, "name": o["name"], "tz": o.get("timezone"), "on": len(people), "scheduled": scheduled, "missing": missing,
                    "outside": sum(1 for p in people if p["outside"]), "people": people[:CAMPO_VISIBLE],
                    "extra": max(0, len(people) - CAMPO_VISIBLE), "cut": cuts.get(lid)})
    return out


async def _plan_by_op(r: od.Reader, cid: str, now: datetime, ops: list[dict]) -> dict[str, tuple[Optional[int], Optional[int]]]:
    """Por operacion: (personas programadas hoy, sin conectar ahora) del Horario de la semana. Sin horario: (None, None)."""
    out: dict[str, tuple[Optional[int], Optional[int]]] = {}
    if not ops or not await r.has("employee_schedule_slots"):
        return out
    try:
        from app.services import group_reports, work_schedule as ws

        people = await group_reports.people(r.db, cid, [o["id"] for o in ops])
        for o in ops:
            tz = ws.zone(o.get("timezone"))
            today = now.astimezone(tz).date()
            week = await ws.week(r.db, cid, o["id"], ws.week_start(today))
            slots = week.get("slots") or []
            if not week.get("configured") or not slots:
                continue
            started = {x["employee_id"] for x in await r.rows("""
                SELECT DISTINCT employee_id::text AS employee_id FROM workforce_attendance_events
                WHERE company_id = CAST(:c AS uuid) AND lower(event_type) = ANY(:t) AND COALESCE(occurred_at, created_at) >= :s
            """, {"c": cid, "t": list(od.CHECK_IN), "s": datetime(today.year, today.month, today.day, tzinfo=tz)},
                tables=("workforce_attendance_events",)) or []}
            scheduled = missing = 0
            for p in people:
                if p["location_id"] != o["id"]:
                    continue
                plan = ws.day_plan(ws.slot_of(slots, p["slot"]), today)
                if not plan:
                    continue
                scheduled += 1
                begin = ws.parse_hhmm(plan.get("start"))
                if begin and now.astimezone(tz).time() >= begin and p["id"] not in started:
                    missing += 1
            out[o["id"]] = (scheduled, missing)
    except Exception as error:
        log.warning("oficina: horario sin datos (%s)", type(error).__name__)
        await r.db.rollback()
    return out


async def live_campo(r: od.Reader, c: dict, now: datetime, privacy: str) -> dict:
    cid = c["id"]
    tz = od._zone(c.get("timezone"))
    start, _e, _l = of.jornada(now, tz, None)
    ops = await r.rows("SELECT id::text AS id, name, timezone FROM work_locations WHERE company_id = CAST(:c AS uuid) ORDER BY name",
                       {"c": cid}, tables=("work_locations",)) or []
    shifts = await od.open_shifts(r, cid, now)
    gps = await r.rows("""
        SELECT DISTINCT ON (employee_id) employee_id::text AS employee_id,
               lower(COALESCE(payload_json->'punch_location'->>'gps_status', payload_json->>'gps_status', '')) AS gps
        FROM workforce_attendance_events
        WHERE company_id = CAST(:c AS uuid) AND COALESCE(occurred_at, created_at) >= :s
          AND COALESCE(payload_json->'punch_location'->>'gps_status', payload_json->>'gps_status', '') <> ''
        ORDER BY employee_id, COALESCE(occurred_at, created_at) DESC
    """, {"c": cid, "s": start}, tables=("workforce_attendance_events",))
    outside = {person_key(g["employee_id"]) for g in gps or [] if g["gps"] in ("outside", "fuera", "out")}
    cut_rows = await r.rows("""
        SELECT DISTINCT ON (n.location_id) n.location_id::text AS location_id, n.kind, n.created_at AS at,
               (SELECT CASE WHEN bool_or(d.status = 'sent') THEN 'sent' WHEN bool_or(d.status IN ('failed', 'error')) THEN 'failed' ELSE 'pending' END
                FROM wa_report_deliveries d WHERE d.notice_id = n.id AND d.company_id = n.company_id) AS status
        FROM wa_report_notices n
        WHERE n.company_id = CAST(:c AS uuid) AND n.kind IN ('checkin', 'checkout') AND NOT n.test AND n.created_at >= :s
        ORDER BY n.location_id, n.created_at DESC
    """, {"c": cid, "s": now - timedelta(hours=24)}, tables=("wa_report_notices", "wa_report_deliveries"))
    op_tz = {o["id"]: od._zone(o.get("timezone")) for o in ops}
    cuts = {x["location_id"]: cut_out(x, op_tz.get(x["location_id"], tz)) for x in cut_rows or []}
    plan = await _plan_by_op(r, cid, now, ops)
    kpis, _lines = await od.campo_kpis(r, c, now, shifts)
    return _finish({"ok": True, "company_id": cid, "template": "campo", "privacy": privacy,
                    "ops": campo_ops(ops, shifts or [], outside, plan, cuts, privacy), "on_shift": len(shifts) if shifts is not None else None,
                    "kpis": kpis, "brand": await ov.brand(r.db, cid, c.get("settings")),
                    "known": {"staff": shifts is not None, "gps": gps is not None, "cuts": cut_rows is not None}})


# ================================================================== CLONEXA
AREAS = ("direccion", "juntas", "marketing", "ventas", "bots", "tesoreria", "lounge")
IGNORED_FLOWS = ("oficina - estado",)


def area_for_flow(name: Any) -> str:
    """Area de un flujo de n8n nuevo (que no es de ningun agente) por su nombre."""
    n = of.fold(name)
    if re.search(r"venta|correo|prospec|lead|comunidad|whatsapp ventas", n):
        return "ventas"
    if re.search(r"voltage|bot|telegram|aviso|timesheet|carta|error|velvet|asadero", n):
        return "bots"
    if re.search(r"nexa|contenido|tiktok|reel|publica|plan b|calendario|anuncio", n):
        return "marketing"
    return "bots"


def extra_workers(n8n: dict, now: datetime, limit: int = 6) -> list[dict]:
    """Flujos activos de n8n que no son de ningun agente: aparecen solos como trabajadores nuevos en su area."""
    if not n8n.get("ok"):
        return []
    known = {of.fold(f) for a in of.AGENTS for f in a["flows"]} | set(IGNORED_FLOWS)
    out = []
    for w in n8n.get("workflows") or []:
        if not isinstance(w, dict) or not w.get("name") or of.fold(w["name"]) in known or not w.get("active"):
            continue
        out.append({"id": "flujo:" + hashlib.sha256(of.fold(w["name"]).encode()).hexdigest()[:10], "name": ov._short(w["name"], 40),
                    "area": area_for_flow(w["name"]), "state": of.flow_state(w, now), "today": of.flow_lines([w], now)[:3], "extra": True})
    return out[:limit]


def treasury_state(summary: Optional[dict]) -> dict:
    """Estado de cobro SIN montos: al dia / vence en N dias / vencido / sin contrato (funcion pura)."""
    s = summary or {}
    if not s.get("has_contract"):
        return {"state": "sin_contrato", "text": "Sin contrato"}
    if s.get("state") == "en_mora":
        d = int(s.get("days_late") or 0)
        return {"state": "vencido", "text": f"Vencido · {d} {'día' if d == 1 else 'días'}"}
    month = s.get("month") or {}
    if s.get("state") == "en_ventana":
        left = month.get("days_left")
        return {"state": "vence", "text": "Vence hoy" if left == 0 else (f"Vence en {left} {'día' if left == 1 else 'días'}" if left is not None else "En ventana de pago")}
    return {"state": "al_dia", "text": "Al día"}


def health(last_activity_at: Any, now: datetime) -> str:
    at = of.parse_dt(last_activity_at)
    if not at:
        return "nodata"
    hours = (now - at).total_seconds() / 3600
    return "ok" if hours <= 2 else "warn" if hours <= 48 else "bad"


def company_cards(floors: list[dict], now: datetime) -> list[dict]:
    """Una tarjeta por empresa registrada con las mismas cifras de su representante (sin dinero)."""
    return [{"company_id": f["company_id"], "name": f["name"], "template": f["template"], "label": f.get("template_label"),
             "kpis": [list(k) for k in (f.get("kpis") or [])[:2]], "health": health(f.get("last_activity_at"), now)} for f in floors]


async def bots(r: od.Reader, floors: list[dict], now: datetime) -> Optional[list[dict]]:
    """Un trabajador por cada bot de Telegram de las empresas, con su actividad real del dia."""
    rows = await r.rows("""
        SELECT b.company_id::text AS company_id, COALESCE(b.name, '') AS name, COALESCE(b.status, '') AS status, b.last_error IS NOT NULL AND b.last_error <> '' AS failing
        FROM company_bot_instances b WHERE lower(b.channel) = 'telegram'
    """, tables=("company_bot_instances",))
    if rows is None:
        return None
    by = {f["company_id"]: f for f in floors}
    start = now - timedelta(hours=24)
    out = []
    for b in rows:
        f = by.get(b["company_id"])
        if not f:
            continue
        punches = await r.value("SELECT COUNT(*) FROM workforce_attendance_events WHERE company_id = CAST(:c AS uuid) AND COALESCE(occurred_at, created_at) >= :s",
                                {"c": b["company_id"], "s": start}, tables=("workforce_attendance_events",))
        on = (f.get("staff") or {}).get("total")
        state = "err" if b["failing"] else "train" if str(b["status"]).lower() in ("disabled", "inactive", "paused") else ("work" if (on or punches) else "wait")
        today = [f"{on} turnos abiertos" if on is not None else "Turnos: sin datos", f"{punches} marcaciones en 24 h" if punches is not None else "Marcaciones: sin datos"]
        out.append({"id": "bot:" + b["company_id"][:8], "name": f"Bot {f['name']}", "area": "bots", "state": state, "today": today, "bot": True})
    return out


def prospect_map(rows: Optional[list[dict]]) -> Optional[dict]:
    """Mapa comercial: los negocios de la lista de prospeccion (puntos normalizados 0..1) y sus zonas mas
    frecuentes. None = sin datos; nunca puntos inventados."""
    if rows is None:
        return None
    pts = [(float(r["lat"]), float(r["lng"]), str(r.get("status") or "")) for r in rows if r.get("lat") is not None and r.get("lng") is not None]
    zones: dict[str, int] = {}
    for r in rows:
        if r.get("zone"):
            zones[r["zone"]] = zones.get(r["zone"], 0) + 1
    top = [z for z, _ in sorted(zones.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
    if not pts:
        return {"points": [], "zones": top, "count": 0}
    la0, la1 = min(p[0] for p in pts), max(p[0] for p in pts)
    lo0, lo1 = min(p[1] for p in pts), max(p[1] for p in pts)
    span = lambda a, b: (b - a) or 1.0  # noqa: E731
    kind = lambda s: "respondio" if s == "respondio" else "contactado" if s in ("contactado", "enviado") else "nuevo"  # noqa: E731
    return {"points": [[round((p[1] - lo0) / span(lo0, lo1), 3), round(1 - (p[0] - la0) / span(la0, la1), 3), kind(p[2])] for p in pts],
            "zones": top, "count": len(pts)}


async def live_clonexa(r: od.Reader, now: datetime, n8n: dict, base: dict, agents: list[dict], approvals: dict) -> dict:
    floors = base["floors"]

    async def billing_states():
        from app.services import billing

        if not await r.has("billing_contracts"):
            return None
        out = []
        today = now.astimezone(of.BOGOTA).date()
        try:
            for f in floors:
                contract = await billing.get_contract(r.db, f["company_id"])
                items = await billing.installments(r.db, f["company_id"], today) if contract else []
                out.append({"name": f["name"], **treasury_state(billing.summarize(contract, items, today))})
        except Exception as error:
            log.warning("oficina: facturacion sin datos (%s)", type(error).__name__)
            await r.db.rollback()
            return None
        return out
    treasury = await _heavy("billing", billing_states)
    workers = [{**a, "area": of.AGENT_AREA.get(a["id"], "bots")} for a in agents] + extra_workers(n8n, now)
    bot_list = await bots(r, floors, now)
    cal = n8n.get("calendar") if n8n.get("ok") else None
    pts = await r.rows("""
        SELECT p.lat, p.lng, COALESCE(p.status, '') AS status, COALESCE(z.name, '') AS zone FROM prospects p
        LEFT JOIN prospect_zones z ON z.id = p.zone_id
        WHERE NOT p.is_test AND p.lat IS NOT NULL AND p.lng IS NOT NULL ORDER BY p.created_at DESC LIMIT 300
    """, tables=("prospects", "prospect_zones"))
    snap = {"ok": True, "template": "clonexa", "map": prospect_map(pts), "n8n_ok": bool(n8n.get("ok")), "workers": workers + (bot_list or []),
            "bots_known": bot_list is not None, "companies": company_cards(floors, now), "treasury": treasury,
            "approvals": {"pieces": approvals.get("pieces_count"), "batch": bool(approvals.get("batch")) if approvals.get("batch_known") else None,
                          "leads": len(approvals.get("replied") or []) if approvals.get("replied_known") else None},
            "calendar": [{"fecha": x.get("fecha"), "formato": x.get("formato"), "tema": x.get("tema"), "estado": "Por aprobar"}
                         for x in (approvals.get("pieces") or [])[:4]] if cal and cal.get("ok") else None,
            "next": (cal or {}).get("next") if cal and cal.get("ok") else None,
            "radar": await radar_live(r, now)}
    snap["rev"] = ov.rev(snap)
    return snap


async def radar_live(r: od.Reader, now: datetime) -> Optional[dict]:
    """Area Innovacion (NEXUS): estado REAL del Radar (investigando / esperando / error), top 3 del ultimo informe,
    conteos por estado y el proximo informe. Sin la tabla o si falla: None (la oficina muestra "Sin ideas aún")."""
    if not await r.has("radar_informes"):
        return None
    try:
        from app.services import radar

        return await radar.office_snapshot(r.db, now)
    except Exception as error:  # noqa: BLE001 - la oficina nunca se cae por el radar
        log.warning("oficina: radar sin datos (%s)", type(error).__name__)
        await r.db.rollback()
        return None
