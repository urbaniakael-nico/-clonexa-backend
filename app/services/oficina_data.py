"""Oficina 3D: lo que sale de la base (solo lectura, salvo el editor y el orden de pisos).

- Pisos = empresas REGISTRADAS (no demos, no archivadas). Toda consulta de una empresa filtra por
  su company_id; nada de una empresa se mezcla con otra.
- Representante: 4 cifras de ACTIVIDAD del dia segun la plantilla (nunca dinero).
- Personal: solo turnos ABIERTOS (open_shift_alert.open_shifts), con primer nombre + inicial o
  solo el cargo. Nada de GPS en vivo.
- Piso CLONEXA: prospectos, lotes de correo, respuestas, conversaciones Nexa, avisos y timesheets
  de VOLTAGE y la cola de Menu video, para las lineas de "que hizo hoy" y la sala de aprobaciones.
Una tabla que no existe (o una consulta que falla) cuenta como "sin datos", nunca como cero.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import company_kind
from app.services import oficina as of

log = logging.getLogger("clonexa.oficina")

CANCELLED = ("cancelado", "cancelled", "canceled", "merma")
ACTIVE_ORDER = ("pendiente", "alistando", "entregado")
CHECK_IN = ("check_in", "entrada", "start_shift", "shift_start")
CHECK_OUT = ("check_out", "salida", "end_shift", "shift_end")
BREAK_START = ("break_start", "pausa", "pause_start")
BREAK_END = ("break_end", "retomar", "pause_end", "resume")
NO_DATA = "—"


def _settings(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _zone(name: Any) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or "America/Bogota"))
    except Exception:
        return ZoneInfo("America/Bogota")


class Reader:
    """Consultas tolerantes: una tabla que falta o una consulta que falla devuelve None."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._tables: dict[str, bool] = {}

    async def has(self, table: str) -> bool:
        if table not in self._tables:
            try:
                self._tables[table] = bool((await self.db.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": f"public.{table}"})).scalar())
            except Exception:
                await self.db.rollback()
                self._tables[table] = False
        return self._tables[table]

    async def rows(self, sql: str, params: Optional[dict] = None, *, tables: tuple[str, ...] = ()) -> Optional[list[dict]]:
        for t in tables:
            if not await self.has(t):
                return None
        try:
            return [dict(r) for r in (await self.db.execute(text(sql), params or {})).mappings().all()]
        except Exception as error:
            log.warning("oficina: consulta sin datos (%s)", type(error).__name__)
            await self.db.rollback()
            return None

    async def one(self, sql: str, params: Optional[dict] = None, *, tables: tuple[str, ...] = ()) -> Optional[dict]:
        rows = await self.rows(sql, params, tables=tables)
        return rows[0] if rows else ({} if rows is not None else None)

    async def value(self, sql: str, params: Optional[dict] = None, *, tables: tuple[str, ...] = ()) -> Optional[int]:
        row = await self.one(sql, params, tables=tables)
        if row is None:
            return None
        v = next(iter(row.values()), None) if row else None
        return int(v or 0)


# ------------------------------------------------------------------ empresas y pisos
async def registered_companies(r: Reader) -> list[dict]:
    rows = await r.rows("""
        SELECT c.id::text AS id, c.name, c.status, c.timezone, c.settings_json AS settings, c.created_at
        FROM companies c
        WHERE LOWER(COALESCE(c.status, '')) NOT IN ('archived', 'deleted', 'archivada', 'eliminada')
        ORDER BY c.created_at, c.name
    """, tables=("companies",)) or []
    out = []
    for c in rows:
        settings = _settings(c.get("settings"))
        if company_kind.resolve_kind(c["id"], settings) != company_kind.REGISTERED:
            continue
        out.append({**c, "settings": settings})
    if not out:
        return out
    ids = [c["id"] for c in out]
    mods: dict[str, set[str]] = {}
    for m in await r.rows("""
        SELECT cm.company_id::text AS company_id, lower(m.code) AS code FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id::text = ANY(:ids) AND cm.enabled IS TRUE
    """, {"ids": ids}, tables=("company_modules", "modules")) or []:
        mods.setdefault(m["company_id"], set()).add(m["code"])
    places: set[str] = set()
    for p in await r.rows("SELECT DISTINCT company_id::text AS company_id FROM work_locations WHERE company_id::text = ANY(:ids)",
                          {"ids": ids}, tables=("work_locations",)) or []:
        places.add(p["company_id"])
    for c in out:
        c["modules"] = mods.get(c["id"], set())
        c["has_locations"] = c["id"] in places
        c["business_day"] = _business_day(c["settings"])
    return out


def _business_day(settings: dict) -> Optional[dict]:
    raw = settings.get("hospitality_business_day")
    if not isinstance(raw, dict) or raw.get("enabled") is False:
        return None
    return {"open": raw.get("open"), "close": raw.get("close")}


def overnight(cfg: Optional[dict]) -> bool:
    o, c = of.clock((cfg or {}).get("open")), of.clock((cfg or {}).get("close"))
    return bool(o and c and c < o)


async def floor_rows(r: Reader) -> dict[str, dict]:
    rows = await r.rows("SELECT company_id::text AS company_id, orden, plantilla, privacidad, estilo, distribucion, quien_ve, roles_ve, modo_tv, liviano FROM oficina_pisos",
                        tables=("oficina_pisos",))
    if rows is None:  # base sin la migracion 025o (Negocio en vivo 3D)
        rows = await r.rows("SELECT company_id::text AS company_id, orden, plantilla, privacidad, estilo, distribucion FROM oficina_pisos",
                            tables=("oficina_pisos",))
    if rows is None:  # base sin la migracion 025k: lo de la fase 1
        rows = await r.rows("SELECT company_id::text AS company_id, orden, plantilla, privacidad FROM oficina_pisos",
                            tables=("oficina_pisos",)) or []
    return {x["company_id"]: x for x in rows}


def floor_style(row: dict, template: str) -> str:
    """Interruptor por empresa del piso realista (apagado por defecto). Solo plantillas con motor realista."""
    from app.services import oficina_vivo as ov

    wanted = row.get("estilo")
    if wanted == "bar" and template == "bar":
        return "bar"          # el bar aprobado (oficina_bar.js, personajes de Mixamo): hoy solo The Time Machine
    if wanted == "aprobado" and template in APPROVED_TEMPLATES:
        return "aprobado"     # pisos aprobados (025m): Velvet (taller), Asadero (restaurante) y VOLTAGE (campo)
    return "realista" if wanted == "realista" and template in ov.REAL_TEMPLATES else "clasico"


APPROVED_TEMPLATES = ("taller", "restaurante", "campo")


async def clonexa_style(r: Reader) -> str:
    """Interruptor del piso de Clonexa (oficina_ajustes.piso_clonexa): 'aprobado' o 'clasico' (sin la fila)."""
    row = await r.one("SELECT valor FROM oficina_ajustes WHERE clave = 'piso_clonexa'", tables=("oficina_ajustes",))
    return "aprobado" if (row or {}).get("valor") == "aprobado" else "clasico"


async def reception_style(r: Reader) -> str:
    """Interruptor de la Recepcion con Nexa (oficina_ajustes.piso_recepcion, 025n): 'aprobado' o 'clasico'."""
    row = await r.one("SELECT valor FROM oficina_ajustes WHERE clave = 'piso_recepcion'", tables=("oficina_ajustes",))
    return "aprobado" if (row or {}).get("valor") == "aprobado" else "clasico"


def order_floors(companies: list[dict], saved: dict[str, dict]) -> list[dict]:
    """Orden del ascensor (de arriba hacia abajo, debajo de CLONEXA): el guardado primero; las empresas
    nuevas al final por fecha de registro."""
    def key(c: dict):
        o = (saved.get(c["id"]) or {}).get("orden")
        return (0, int(o), "") if o is not None else (1, 0, str(c.get("created_at") or ""))
    return sorted(companies, key=key)


# ------------------------------------------------------------------ actividad por empresa
async def last_activity(r: Reader, cid: str) -> Optional[datetime]:
    moments: list[datetime] = []
    for sql, tables in (
        ("SELECT MAX(last_seen_at) AS at FROM clonexa_access_sessions WHERE company_id = CAST(:c AS uuid)", ("clonexa_access_sessions",)),
        ("SELECT MAX(created_at) AS at FROM hospitality_orders WHERE company_id = CAST(:c AS uuid)", ("hospitality_orders",)),
        ("SELECT MAX(COALESCE(occurred_at, created_at)) AS at FROM workforce_attendance_events WHERE company_id = CAST(:c AS uuid)",
         ("workforce_attendance_events",)),
    ):
        row = await r.one(sql, {"c": cid}, tables=tables)
        at = of.parse_dt((row or {}).get("at"))
        if at:
            moments.append(at)
    return max(moments) if moments else None


async def open_shifts(r: Reader, cid: str, now: datetime) -> Optional[list[dict]]:
    if not await r.has("workforce_attendance_status") or not await r.has("employees"):
        return None
    from app.services import open_shift_alert

    try:
        return await open_shift_alert.open_shifts(r.db, cid, now_utc=now)
    except Exception as error:
        log.warning("oficina: turnos abiertos sin datos (%s)", type(error).__name__)
        await r.db.rollback()
        return None


def minutes_worked(events: list[dict], start: datetime, now: datetime, working_at_start: dict[str, bool]) -> int:
    """Minutos trabajados en [start, now) por todo el personal (sin pausas). Funcion pura.
    events: {employee_id, type, at} ordenados por hora; working_at_start: quien ya estaba trabajando."""
    total = 0.0
    by: dict[str, list[dict]] = {}
    for e in events:
        by.setdefault(str(e["employee_id"]), []).append(e)
    for emp in set(by) | {k for k, v in working_at_start.items() if v}:
        since = start if working_at_start.get(emp) else None
        for e in sorted(by.get(emp, []), key=lambda x: x["at"]):
            kind, at = str(e["type"]).lower(), max(start, min(now, e["at"]))
            if kind in CHECK_IN or kind in BREAK_END:
                since = since or at
            elif kind in CHECK_OUT or kind in BREAK_START:
                if since:
                    total += (at - since).total_seconds()
                since = None
        if since:
            total += (now - since).total_seconds()
    return int(max(0.0, total) // 60)


async def hours_today(r: Reader, cid: str, start: datetime, now: datetime, shifts: list[dict]) -> Optional[int]:
    rows = await r.rows("""
        SELECT employee_id::text AS employee_id, lower(event_type) AS type, COALESCE(occurred_at, created_at) AS at
        FROM workforce_attendance_events
        WHERE company_id = CAST(:c AS uuid) AND COALESCE(occurred_at, created_at) >= :s AND COALESCE(occurred_at, created_at) < :n
        ORDER BY COALESCE(occurred_at, created_at)
    """, {"c": cid, "s": start, "n": now}, tables=("workforce_attendance_events",))
    if rows is None:
        return None
    before = {str(s["employee_id"]): True for s in shifts if s.get("check_in_at") and s["check_in_at"] < start}
    events = [{"employee_id": x["employee_id"], "type": x["type"], "at": of.parse_dt(x["at"])} for x in rows if of.parse_dt(x["at"])]
    return minutes_worked(events, start, now, before)


def _num(value: Optional[int]) -> str:
    return NO_DATA if value is None else str(value)


async def taller_kpis(r: Reader, c: dict, now: datetime, shifts: Optional[list[dict]]) -> tuple[list, list]:
    tz = _zone(c.get("timezone"))
    start, _end, _label = of.jornada(now, tz, None)
    minutes = await hours_today(r, c["id"], start, now, shifts or []) if shifts is not None else None
    lot, progress, lines = NO_DATA, NO_DATA, []
    if await r.has("product_references"):
        try:
            from app.services import references_v2

            groups = await references_v2.reference_groups(r.db, c["id"])
            live = [g for g in groups if any(line.get("bot_active") for line in g["lines"]) and g.get("received")]
            live.sort(key=lambda g: ((g.get("cuts_by_date") or [{}])[0].get("date") or "", g.get("received") or 0), reverse=True)
            if live:
                g = live[0]
                lot = g["name"]
                progress = f"{g['percent']:g}%" if g.get("percent") is not None else NO_DATA
                lines.append(f"Lote activo {g['name']}: {g['produced']} de {g['received']} producidas")
        except Exception as error:
            log.warning("oficina: referencias sin datos (%s)", type(error).__name__)
            await r.db.rollback()
    hours = NO_DATA if minutes is None else f"{minutes // 60}:{minutes % 60:02d} h"
    return [["Personas en turno", _num(len(shifts) if shifts is not None else None)], ["Horas del día", hours],
            ["Lote activo", lot], ["Avance del lote", progress]], lines


async def restaurante_kpis(r: Reader, c: dict, now: datetime, shifts: Optional[list[dict]]) -> tuple[list, list]:
    tz = _zone(c.get("timezone"))
    start, end, _label = of.jornada(now, tz, c.get("business_day"))
    p = {"c": c["id"], "s": start, "e": end, "x": list(CANCELLED), "a": list(ACTIVE_ORDER), "recent": now - timedelta(hours=24)}
    row = await r.one("""
        SELECT COUNT(*) FILTER (WHERE created_at >= :s AND created_at < :e AND lower(status) <> ALL(:x)) AS pedidos,
               COUNT(*) FILTER (WHERE created_at >= :s AND created_at < :e AND lower(status) <> ALL(:x) AND lower(order_type) = 'domicilio') AS domicilios,
               COUNT(*) FILTER (WHERE status IN ('pendiente', 'alistando') AND archived_at IS NULL AND cancelled_at IS NULL AND created_at >= :recent) AS cocina
        FROM hospitality_orders WHERE company_id = CAST(:c AS uuid) AND created_at >= LEAST(:s, :recent)
    """, p, tables=("hospitality_orders",))
    get = (lambda k: None) if row is None else (lambda k: int(row.get(k) or 0))
    return [["Pedidos del día", _num(get("pedidos"))], ["En cocina ahora", _num(get("cocina"))], ["Domicilios del día", _num(get("domicilios"))],
            ["Personal en turno", _num(len(shifts) if shifts is not None else None)]], []


async def bar_kpis(r: Reader, c: dict, now: datetime, shifts: Optional[list[dict]]) -> tuple[list, list]:
    tz = _zone(c.get("timezone"))
    cfg = c.get("business_day") if overnight(c.get("business_day")) else of.BAR_DEFAULT_DAY
    start, end, label = of.jornada(now, tz, cfg)
    p = {"c": c["id"], "s": start, "e": end, "x": list(CANCELLED), "recent": now - timedelta(hours=24)}
    row = await r.one("""
        SELECT COUNT(*) FILTER (WHERE created_at >= :s AND created_at < :e AND lower(status) <> ALL(:x)) AS pedidos,
               COUNT(DISTINCT table_key) FILTER (WHERE status IN ('pendiente', 'alistando', 'entregado') AND archived_at IS NULL
                                                   AND cancelled_at IS NULL AND lower(order_type) <> 'domicilio' AND created_at >= :recent) AS mesas
        FROM hospitality_orders WHERE company_id = CAST(:c AS uuid) AND created_at >= LEAST(:s, :recent)
    """, p, tables=("hospitality_orders",))
    songs = await r.value("""
        SELECT COUNT(*) FROM hospitality_song_requests WHERE company_id = CAST(:c AS uuid) AND created_at >= :s AND created_at < :e
    """, p, tables=("hospitality_song_requests",))
    get = (lambda k: None) if row is None else (lambda k: int(row.get(k) or 0))
    local = lambda d: d.astimezone(tz).strftime("%d/%m %H:%M")  # noqa: E731
    return [["Mesas abiertas", _num(get("mesas"))], ["Pedidos a barra", _num(get("pedidos"))], ["Canciones pedidas", _num(songs)],
            ["Personal en turno", _num(len(shifts) if shifts is not None else None)]], [f"{label}: {local(start)} a {local(end)}"]


async def _missing_now(r: Reader, cid: str, now: datetime, ops: list[dict]) -> Optional[int]:
    """Personas con franja del Horario de la semana ya empezada hoy que no iniciaron turno (por operacion)."""
    try:
        from app.services import group_reports, work_schedule as ws
    except Exception:
        return None
    if not await r.has("employee_schedule_slots"):
        return None
    try:
        total, configured = 0, False
        people = await group_reports.people(r.db, cid, [o["id"] for o in ops])
        for o in ops:
            tz = ws.zone(o.get("timezone"))
            today = now.astimezone(tz).date()
            week = await ws.week(r.db, cid, o["id"], ws.week_start(today))
            slots = week.get("slots") or []
            if not week.get("configured") or not slots:
                continue
            configured = True
            started = {x["employee_id"] for x in await r.rows("""
                SELECT DISTINCT employee_id::text AS employee_id FROM workforce_attendance_events
                WHERE company_id = CAST(:c AS uuid) AND lower(event_type) = ANY(:t) AND COALESCE(occurred_at, created_at) >= :s
            """, {"c": cid, "t": list(CHECK_IN), "s": datetime(today.year, today.month, today.day, tzinfo=tz)}, tables=("workforce_attendance_events",)) or []}
            for p in people:
                if p["location_id"] != o["id"] or p["id"] in started:
                    continue
                plan = ws.day_plan(ws.slot_of(slots, p["slot"]), today)
                begin = ws.parse_hhmm((plan or {}).get("start"))
                if plan and begin and now.astimezone(tz).time() >= begin:
                    total += 1
        return total if configured else None
    except Exception as error:
        log.warning("oficina: sin conectar sin datos (%s)", type(error).__name__)
        await r.db.rollback()
        return None


async def campo_kpis(r: Reader, c: dict, now: datetime, shifts: Optional[list[dict]]) -> tuple[list, list]:
    tz = _zone(c.get("timezone"))
    start, _end, _label = of.jornada(now, tz, None)
    ops = await r.rows("SELECT id::text AS id, name, timezone FROM work_locations WHERE company_id = CAST(:c AS uuid) ORDER BY name",
                       {"c": c["id"]}, tables=("work_locations",)) or []
    per_op: dict[str, int] = {}
    for s in shifts or []:
        name = str(s.get("work_location_name") or "").strip() or "Sin lugar"
        per_op[name] = per_op.get(name, 0) + 1
    names = [o["name"] for o in ops if o.get("name")] or sorted(per_op)
    shown = names[:2]
    on_value = NO_DATA if shifts is None else " · ".join(str(per_op.get(n, 0)) for n in shown) or str(len(shifts))
    on_label = ("En turno · " + " / ".join(shown)) if shown else "En turno"
    outside = await r.value("""
        SELECT COUNT(DISTINCT employee_id) FROM workforce_attendance_events
        WHERE company_id = CAST(:c AS uuid) AND COALESCE(occurred_at, created_at) >= :s
          AND lower(COALESCE(payload_json->'punch_location'->>'gps_status', payload_json->>'gps_status', '')) IN ('outside', 'fuera', 'out')
    """, {"c": c["id"], "s": start}, tables=("workforce_attendance_events",))
    sheets = await r.value("SELECT COUNT(*) FROM wa_timesheet_receipts WHERE company_id = CAST(:c AS uuid) AND received_at >= :s",
                           {"c": c["id"], "s": start}, tables=("wa_timesheet_receipts",))
    missing = await _missing_now(r, c["id"], now, ops) if ops else None
    lines = [f"{n}: {per_op.get(n, 0)} en turno" for n in names]
    if per_op.get("Sin lugar"):
        lines.append(f"Sin lugar asignado: {per_op['Sin lugar']} en turno")
    return [[on_label, on_value], ["Sin conectar", _num(missing)], ["Fuera de perímetro", _num(outside)],
            ["Timesheets recibidos hoy", _num(sheets)]], lines


async def general_kpis(r: Reader, c: dict, now: datetime, shifts: Optional[list[dict]]) -> tuple[list, list]:
    return [["Personas en turno", _num(len(shifts) if shifts is not None else None)]], []


KPI = {"taller": taller_kpis, "restaurante": restaurante_kpis, "bar": bar_kpis, "campo": campo_kpis, "general": general_kpis}


async def floors(r: Reader, now: datetime) -> list[dict]:
    companies = await registered_companies(r)
    saved = await floor_rows(r)
    return [await floor_out(r, c, saved.get(c["id"]) or {}, index, now) for index, c in enumerate(order_floors(companies, saved))]


async def floor_for(r: Reader, company_id: str, now: datetime) -> Optional[dict]:
    """El piso de UNA empresa registrada (Negocio en vivo 3D: el cliente solo ve el suyo). None si no existe."""
    c = next((x for x in await registered_companies(r) if x["id"] == str(company_id)), None)
    if not c:
        return None
    return await floor_out(r, c, (await floor_rows(r)).get(c["id"]) or {}, 0, now)


async def floor_out(r: Reader, c: dict, row: dict, index: int, now: datetime) -> dict:
    deduced = of.deduce_template(c["id"], c["modules"], has_locations=c["has_locations"], overnight=overnight(c.get("business_day")))
    template = row.get("plantilla") or deduced or "general"
    privacy = row.get("privacidad") if row.get("privacidad") in of.PRIVACY else "nombre"
    style = floor_style(row, template)
    shifts = await open_shifts(r, c["id"], now)
    kpis, lines = await KPI[template](r, c, now, shifts)
    last = await last_activity(r, c["id"])
    if template == "general":
        kpis.append(["Última actividad", of.ago_label(last, now)])
    return {
        "company_id": c["id"], "name": c["name"] or "Empresa", "template": template, "template_label": of.TEMPLATE_LABEL[template],
        "template_source": "manual" if row.get("plantilla") else ("auto" if deduced else "sin_deducir"),
        "needs_template": not row.get("plantilla") and not deduced, "privacy": privacy, "order": index,
        "style": style, "style_wanted": row.get("estilo") or "clasico",
        "brand": await _brand(r, c) if style in ("realista", "bar", "aprobado") else None,
        "kpis": kpis, "lines": lines, "last_activity_at": of.iso(last), "last_activity": of.ago_label(last, now),
        "staff": of.staff_out(shifts or [], template, privacy) if shifts is not None else {"total": None, "visible": [], "extra": 0, "ops": []},
    }


async def _brand(r: Reader, c: dict) -> Optional[dict]:
    from app.services import oficina_vivo as ov

    try:
        return await ov.brand(r.db, c["id"], c.get("settings"))
    except Exception as error:
        log.warning("oficina: marca sin datos (%s)", type(error).__name__)
        await r.db.rollback()
        return None


# ------------------------------------------------------------------ piso CLONEXA (base)
async def clonexa_block(r: Reader, now: datetime) -> dict:
    """Lineas reales por agente, sala de aprobaciones (parte de la base) y eventos para la actividad."""
    start = datetime.combine(now.astimezone(of.BOGOTA).date(), datetime.min.time(), of.BOGOTA)
    today = start.date()
    lines: dict[str, list[str]] = {}
    p = {"s": start, "d": today, "since": now - timedelta(hours=24)}

    wa = await r.one("""
        SELECT COUNT(*) FILTER (WHERE last_message_at >= :s) AS hoy, COUNT(*) FILTER (WHERE created_at >= :s) AS nuevas,
               COUNT(*) FILTER (WHERE stage = 'pidio_persona') AS persona, COUNT(*) FILTER (WHERE stage = 'demo_agendada') AS demos
        FROM wa_contacts
    """, p, tables=("wa_contacts",))
    if wa is not None:
        lines["ventas"] = [f"{int(wa.get('hoy') or 0)} conversaciones con mensajes hoy", f"{int(wa.get('nuevas') or 0)} contactos nuevos hoy",
                           f"{int(wa.get('demos') or 0)} con demo agendada · {int(wa.get('persona') or 0)} piden una persona"]

    batch = await r.one("SELECT status, item_count FROM prospect_batches WHERE local_date = :d", p, tables=("prospect_batches",))
    mail = await r.one("""
        SELECT COUNT(*) FILTER (WHERE sent_at >= :s AND channel = 'email') AS enviados,
               COUNT(*) FILTER (WHERE created_at >= :s AND kind = 'respuesta') AS respuestas,
               COUNT(*) FILTER (WHERE created_at >= :s AND kind = 'baja') AS bajas
        FROM prospect_contacts
    """, p, tables=("prospect_contacts",))
    if batch is not None or mail is not None:
        out = []
        if batch:
            out.append(f"Lote de hoy: {int(batch.get('item_count') or 0)} negocios ({batch.get('status')})")
        elif batch is not None:
            out.append("Hoy aún no hay lote de correos")
        if mail:
            out.append(f"{int(mail.get('enviados') or 0)} correos enviados hoy · {int(mail.get('respuestas') or 0)} respuestas · {int(mail.get('bajas') or 0)} bajas")
        lines["correos"] = out

    pros = await r.one("""
        SELECT COUNT(*) FILTER (WHERE created_at >= :s AND NOT is_test) AS nuevos,
               COUNT(*) FILTER (WHERE created_at >= :s AND NOT is_test AND email <> '') AS con_correo,
               COUNT(*) FILTER (WHERE NOT is_test) AS total
        FROM prospects
    """, p, tables=("prospects",))
    if pros is not None:
        lines["prospecta"] = [f"{int(pros.get('nuevos') or 0)} negocios nuevos hoy ({int(pros.get('con_correo') or 0)} con correo publicado)",
                              f"{int(pros.get('total') or 0)} negocios en la lista"]

    sends = await r.value("SELECT COUNT(*) FROM wa_report_deliveries WHERE sent_at >= :s AND NOT test", p, tables=("wa_report_deliveries",))
    if sends is not None:
        lines["mensajero"] = [f"{sends} avisos entregados hoy (cortes, resúmenes y timesheets)"]
    sheets = await r.value("SELECT COUNT(*) FROM wa_timesheet_receipts WHERE received_at >= :s", p, tables=("wa_timesheet_receipts",))
    if sheets is not None:
        lines["archivista"] = [f"{sheets} timesheets recibidos hoy"]
    jobs = await r.one("""
        SELECT COUNT(*) FILTER (WHERE status IN ('en_cola', 'procesando')) AS cola, COUNT(*) FILTER (WHERE finished_at >= :s) AS hechos
        FROM menu_media_jobs
    """, p, tables=("menu_media_jobs",))
    reading = await r.value("SELECT COUNT(*) FROM menu_video_imports WHERE status = 'leyendo'", p, tables=("menu_video_imports",))
    if jobs is not None or reading is not None:
        out = []
        if jobs is not None:
            out.append(f"Cola de Menú video: {int(jobs.get('cola') or 0)} clips en cola · {int(jobs.get('hechos') or 0)} hechos hoy")
        if reading is not None:
            out.append(f"{reading} cartas leyéndose ahora")
        lines["lector"] = out

    replied = await r.rows("""
        SELECT name, replied_at FROM prospects WHERE status = 'respondio' AND NOT is_test ORDER BY replied_at DESC NULLS LAST LIMIT 5
    """, p, tables=("prospects",))
    approvals = {"batch": ({"items": int(batch.get("item_count") or 0)} if batch and batch.get("status") == "pendiente" else None),
                 "batch_known": batch is not None, "replied": [x["name"] for x in replied or []], "replied_known": replied is not None}

    feed: list[dict] = []
    for x in await r.rows("SELECT created_at AS at FROM wa_contacts WHERE created_at >= :since ORDER BY created_at DESC LIMIT 5", p,
                          tables=("wa_contacts",)) or []:
        feed.append({"at": of.iso(x["at"]), "kind": "lead", "text": "<b>Nexa Ventas</b> · nuevo contacto por WhatsApp"})
    for x in await r.rows("""
        SELECT name, replied_at AS at FROM prospects WHERE replied_at >= :since AND NOT is_test ORDER BY replied_at DESC LIMIT 5
    """, p, tables=("prospects",)) or []:
        feed.append({"at": of.iso(x["at"]), "kind": "lead", "text": f"<b>Prospectora</b> · respondió {_esc(x['name'])}"})
    for x in await r.rows("SELECT received_at AS at FROM wa_timesheet_receipts WHERE received_at >= :since ORDER BY received_at DESC LIMIT 3", p,
                          tables=("wa_timesheet_receipts",)) or []:
        feed.append({"at": of.iso(x["at"]), "kind": "run", "text": "<b>Archivista</b> · llegó un timesheet"})
    return {"lines": lines, "approvals": approvals, "feed": feed}


def _esc(value: Any) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


async def shift_feed(r: Reader, floors_out: list[dict], now: datetime, limit: int = 8) -> list[dict]:
    """Turnos iniciados en las ultimas 24 h (por empresa, con su privacidad)."""
    out: list[dict] = []
    for f in floors_out:
        rows = await r.rows("""
            SELECT COALESCE(e.full_name, '') AS name, COALESCE(e.role, '') AS role, COALESCE(ev.occurred_at, ev.created_at) AS at
            FROM workforce_attendance_events ev JOIN employees e ON e.id = ev.employee_id AND e.company_id = ev.company_id
            WHERE ev.company_id = CAST(:c AS uuid) AND lower(ev.event_type) = ANY(:t) AND COALESCE(ev.occurred_at, ev.created_at) >= :since
            ORDER BY COALESCE(ev.occurred_at, ev.created_at) DESC LIMIT :n
        """, {"c": f["company_id"], "t": list(CHECK_IN), "since": now - timedelta(hours=24), "n": limit},
            tables=("workforce_attendance_events", "employees")) or []
        for x in rows:
            who = of.role_label(x["role"]) if f["privacy"] == "cargo" or not of.short_name(x["name"]) else of.short_name(x["name"])
            out.append({"at": of.iso(x["at"]), "kind": "shift", "text": f"<b>{_esc(f['name'])}</b> · {_esc(who)} inició turno"})
    out.sort(key=lambda e: e["at"] or "", reverse=True)
    return out[:limit]


# ------------------------------------------------------------------ editor (oficina_personajes)
CHAR_COLS = ("clave", "nombre", "rol", "tarea", "estilo", "color_ropa", "color_pantalon", "color_pelo", "color_piel", "accesorio",
             "color_accesorio", "cuerpo", "peinado", "genero", "personaje", "tunica", "barba", "color_barba", "updated_at")
OUT_COLS = tuple(k for k in CHAR_COLS if k not in ("clave", "updated_at"))


async def characters(r: Reader) -> list[dict]:
    rows = await r.rows(f"""
        SELECT company_id::text AS company_id, {', '.join(CHAR_COLS)} FROM oficina_personajes ORDER BY company_id NULLS FIRST, clave
    """, tables=("oficina_personajes",)) or []
    return [character_out(x) for x in rows]


def character_out(x: dict) -> dict:
    """Lo guardado de un personaje. Imagen y modelo ya no se usan: no salen (aunque sigan en la base)."""
    out = {"company_id": x.get("company_id"), "clave": x["clave"], **{k: x.get(k) or "" for k in OUT_COLS},
           "updated_at": of.iso(x.get("updated_at"))}
    if out["estilo"] not in of.STYLES:
        out["estilo"] = ""
    if out["accesorio"] not in of.ACCESSORIES:
        out["accesorio"] = ""
    return out


async def company_exists(db: AsyncSession, company_id: Optional[str]) -> bool:
    if company_id is None:
        return True
    return bool((await db.execute(text("SELECT 1 FROM companies WHERE id = CAST(:c AS uuid)"), {"c": company_id})).scalar())


async def get_character(db: AsyncSession, company_id: Optional[str], clave: str) -> Optional[dict]:
    row = (await db.execute(text(f"""
        SELECT company_id::text AS company_id, {', '.join(CHAR_COLS)} FROM oficina_personajes
        WHERE COALESCE(company_id::text, '') = :c AND clave = :k
    """), {"c": company_id or "", "k": clave})).mappings().first()
    return dict(row) if row else None


async def save_character(db: AsyncSession, company_id: Optional[str], clave: str, fields: dict, actor: str) -> dict:
    cols = [k for k in fields if k in CHAR_COLS]
    params = {"c": company_id, "k": clave, "a": actor[:120], **{k: fields[k] for k in cols}}
    sets = ", ".join([f"{k} = EXCLUDED.{k}" for k in cols] + ["updated_by = EXCLUDED.updated_by", "updated_at = now()"])
    names = ", ".join(["company_id", "clave", "updated_by", *cols])
    values = ", ".join(["CAST(:c AS uuid)", ":k", ":a", *[f":{k}" for k in cols]])
    await db.execute(text(f"""
        INSERT INTO oficina_personajes ({names}) VALUES ({values})
        ON CONFLICT ((COALESCE(company_id::text, '')), clave) DO UPDATE SET {sets}
    """), params)
    await db.commit()
    return await get_character(db, company_id, clave) or {}


async def save_floor(db: AsyncSession, company_id: str, *, plantilla: Any = ..., privacidad: Any = ..., estilo: Any = ...,
                     distribucion: Any = ..., actor: str) -> None:
    fields: dict[str, Any] = {}
    if plantilla is not ...:
        fields["plantilla"] = plantilla
    if privacidad is not ...:
        fields["privacidad"] = privacidad
    if estilo is not ...:
        fields["estilo"] = estilo
    if distribucion is not ...:
        fields["distribucion"] = json.dumps(distribucion)
    if not fields:
        return
    cols = list(fields)
    await db.execute(text(f"""
        INSERT INTO oficina_pisos (company_id, updated_by, {', '.join(cols)})
        VALUES (CAST(:c AS uuid), :a, {', '.join(('CAST(:' + k + ' AS jsonb)') if k == 'distribucion' else (':' + k) for k in cols)})
        ON CONFLICT (company_id) DO UPDATE SET {', '.join(f'{k} = EXCLUDED.{k}' for k in cols)}, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"c": company_id, "a": actor[:120], **fields})
    await db.commit()


async def save_order(db: AsyncSession, company_ids: list[str], actor: str) -> None:
    for index, cid in enumerate(company_ids):
        await db.execute(text("""
            INSERT INTO oficina_pisos (company_id, orden, updated_by) VALUES (CAST(:c AS uuid), :o, :a)
            ON CONFLICT (company_id) DO UPDATE SET orden = EXCLUDED.orden, updated_by = EXCLUDED.updated_by, updated_at = now()
        """), {"c": cid, "o": index, "a": actor[:120]})
    await db.commit()


async def floor_row(db: AsyncSession, company_id: str) -> dict:
    return (await floor_rows(Reader(db))).get(company_id) or {}


async def registered_ids(db: AsyncSession) -> set[str]:
    return {c["id"] for c in await registered_companies(Reader(db))}


def counts_now(floors_out: list[dict]) -> int:
    return sum(int((f.get("staff") or {}).get("total") or 0) for f in floors_out)


__all__ = ["Reader", "floors", "clonexa_block", "shift_feed", "characters", "save_character", "save_floor", "save_order",
           "minutes_worked", "order_floors", "registered_companies", "counts_now"]
