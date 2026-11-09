"""Avisos automaticos por WhatsApp a grupos, supervisor y dueños (072A).

Interruptor por empresa ``whatsapp_group_reports`` (settings del modulo workforce), apagado por
defecto. Hoy solo VOLTAGE. Necesita work_schedule (las horas de cada franja salen del Horario de
la semana de cada operacion) y us_payroll (las horas de los resumenes son las de Nomina).

Que se envia y cuando (lo decide este modulo; n8n solo entrega):
- Corte de entrada: entrada + 30 min de cada franja (Horario 1, 2...) de cada operacion, al grupo.
- Corte de salida: salida + 30 min de cada franja, al grupo.
- Timesheet: al supervisor (WhatsApp privado) despues de la ultima salida de SU operacion; al grupo
  de la operacion semanal cada viernes; si al dia siguiente a las 9:00 (hora de la operacion) no
  llego la foto, un solo recordatorio mas.
- Dueños: resumen del dia por WhatsApp + planilla PDF por correo, 30 min despues de la ultima
  salida del dia; totales de la semana (domingo a sabado, FLSA) el lunes 8:00 ET: dueños WhatsApp +
  correo con PDF y Excel; grupos solo horas por persona (sin dinero).
- Un dia sin horario programado (sabado, domingo, dia libre) solo tiene avisos si alguien de esa
  franja inicio turno ese dia.
- MODO PRUEBA (por defecto): todo WhatsApp va al chat del propio numero y todo correo al de
  Clonexa, con el prefijo [PRUEBA].
Sin duplicados: cada aviso se reclama con INSERT ... ON CONFLICT DO NOTHING sobre una clave unica
(tipo + operacion + fecha + franja), en la misma transaccion que sus envios; cada envio se toma con
FOR UPDATE SKIP LOCKED. Un reinicio o dos copias corriendo no mandan nada dos veces.
Toda consulta filtra por company_id.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import os
import random
import re
import time as _time
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import us_time
from app.services import work_schedule as ws

log = logging.getLogger("clonexa.group_reports")

KEY = "whatsapp_group_reports"
MODULE = "workforce"
LOOP_SECONDS = 60
CUT_WINDOW = timedelta(minutes=60)      # despues de esto un corte atrasado ya no sale
WEEKLY_WINDOW = timedelta(hours=3)
MAX_ATTEMPTS = 3
RETRY_AFTER = (timedelta(minutes=2), timedelta(minutes=10))
SEND_GAP = (3.0, 6.0)                   # segundos entre mensajes (para no arriesgar bloqueo)
MAX_SENDS_PER_PASS = 25
PURGE_DAYS = 120
LINK_TTL = timedelta(hours=2)
HTTP_TIMEOUT = 90.0
ENV_URL = "GROUP_REPORTS_N8N_URL"
ENV_SECRET = "GROUP_REPORTS_N8N_SECRET"
SECRET_HEADER = "X-Clonexa-Secret"
TEST_PREFIX = "[PRUEBA] "
EXCLUDED_ROLES = {"gerencia", "director", "gerente", "manager", "management",
                  "company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario"}

KINDS = {
    "checkin": "Corte de entrada",
    "checkout": "Corte de salida",
    "ts_daily": "Timesheet: recordatorio al supervisor",
    "ts_weekly": "Timesheet: recordatorio semanal al grupo",
    "ts_followup": "Timesheet: recordatorio de las 9:00",
    "owners_daily": "Resumen del día a dueños",
    "weekly_totals": "Totales de la semana",
}
EXTRA_KINDS = {"received": "Timesheet recibido"}
# 074A: lo UNICO que puede llegar a un grupo de WhatsApp. Totales y resumenes nunca van a grupos.
GROUP_KINDS = frozenset({"checkin", "checkout", "ts_weekly", "ts_followup"})
DAY_ES = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
DAY_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
TIMEZONES = ("America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Bogota")

DEFAULT_CONFIG: dict[str, Any] = {
    "test_mode": True,
    "own_number": "",
    "clonexa_email": "",
    "operations": [],          # [{"location_id", "group_jid", "group_name"}]
    "supervisor": {"name": "", "phone": "", "email": "", "location_id": ""},
    "owners": [],              # [{"name", "phone", "email"}]
    "weekly_location_id": "",  # operacion que recibe el recordatorio semanal (Virginia)
    "weekly_weekday": 4,       # viernes
    "followup_time": "09:00",
    "checkin_after_min": 30,
    "checkout_after_min": 30,
    "summary_after_min": 30,
    "totals_weekday": 0,       # lunes
    "totals_time": "08:00",
    "totals_tz": "America/New_York",
    "kinds": {k: True for k in KINDS},
    "drive_folders": {},       # {"<location_id>" | "_other": "<id de carpeta en Drive>"}
}


class Invalid(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


# ------------------------------------------------------------------ reglas puras
def hm(minutes: Any) -> str:
    m = max(0, int(round(float(minutes or 0))))
    h, r = divmod(m, 60)
    if not h:
        return f"{r} min"
    return f"{h} h" if not r else f"{h} h {r:02d} min"


def day_es(d: date) -> str:
    return f"{DAY_ES[d.weekday()]} {d.day:02d}/{d.month:02d}"


def day_en(d: date) -> str:
    return f"{DAY_EN[d.weekday()]} {d.month:02d}/{d.day:02d}"


DAY_FULL_ES = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
PARTICLES = {"de", "del", "la", "las", "los", "y", "e", "da", "das", "do", "dos", "van", "von"}
HTML_MARK = "<!--html-->"
LONG_SHIFT_MIN = 12 * 60
RULE = "━━━━━━━━━━"


def day_full(d: date) -> str:
    return f"{DAY_FULL_ES[d.weekday()]} {d.day:02d}/{d.month:02d}"


def clean_name(raw: Any) -> str:
    """Nombre para mostrar: sin comillas ni comillas invertidas, sin espacios de mas y con mayusculas
    de nombre propio ("de", "del", "la"... en minuscula). No cambia la base."""
    s = re.sub(r"[\"`´“”«»]", "", str(raw or ""))
    s = re.sub(r"(?<![A-Za-zÀ-ÿ])'|'(?![A-Za-zÀ-ÿ])", "", s)
    words = []
    for i, word in enumerate(s.split()):
        low = word.lower()
        if i and low in PARTICLES:
            words.append(low)
            continue
        words.append("-".join("'".join(q[:1].upper() + q[1:].lower() for q in part.split("'")) for part in word.split("-")))
    return " ".join(words) or "—"


def numbered(items: list[str]) -> str:
    return "\n".join(f"{i}. {x}" for i, x in enumerate(items, 1))


def digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def clean_phone(value: Any, field: str) -> str:
    d = digits(value)
    if d and not 8 <= len(d) <= 15:
        raise Invalid(field, "Número de WhatsApp no válido (con código de país, solo dígitos).")
    return d


EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def clean_email(value: Any, field: str) -> str:
    v = str(value or "").strip().lower()
    if v and not EMAIL_RE.match(v):
        raise Invalid(field, "Correo no válido.")
    return v


def clean_hhmm(value: Any, field: str) -> str:
    t = ws.parse_hhmm(value)
    if t is None:
        raise Invalid(field, "Hora no válida (HH:MM).")
    return ws.hhmm(t)


def clean_int(value: Any, field: str, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise Invalid(field, "Número no válido.") from None
    if not lo <= n <= hi:
        raise Invalid(field, f"Debe estar entre {lo} y {hi}.")
    return n


def _text(value: Any, size: int) -> str:
    return " ".join(str(value or "").split())[:size]


def merge_config(raw: Any) -> dict:
    """Lo guardado sobre los valores por defecto (llaves nuevas quedan con su defecto)."""
    raw = ws.settings_dict(raw)
    out = json.loads(json.dumps(DEFAULT_CONFIG))
    for k, v in raw.items():
        if k in out:
            out[k] = v
    out["kinds"] = {**DEFAULT_CONFIG["kinds"], **(raw.get("kinds") if isinstance(raw.get("kinds"), dict) else {})}
    out["supervisor"] = {**DEFAULT_CONFIG["supervisor"], **(raw.get("supervisor") if isinstance(raw.get("supervisor"), dict) else {})}
    return out


def clean_config(body: Any, location_ids: set[str]) -> dict:
    """Lo que manda el portal -> lo que se guarda. Valida todo en el servidor."""
    body = body if isinstance(body, dict) else {}
    cfg = merge_config(body)
    out: dict[str, Any] = {"test_mode": cfg.get("test_mode") is not False}
    out["own_number"] = clean_phone(cfg.get("own_number"), "own_number")
    out["clonexa_email"] = clean_email(cfg.get("clonexa_email"), "clonexa_email")
    ops, seen = [], set()
    for item in cfg.get("operations") or []:
        item = item if isinstance(item, dict) else {}
        lid = str(item.get("location_id") or "")
        if lid not in location_ids:
            raise Invalid("operations", "Esa operación no existe en esta empresa.")
        if lid in seen:
            continue
        seen.add(lid)
        jid = str(item.get("group_jid") or "").strip()
        if jid and not re.fullmatch(r"[0-9-]{6,40}@g\.us", jid):
            raise Invalid("operations", "ID de grupo no válido (termina en @g.us).")
        ops.append({"location_id": lid, "group_jid": jid, "group_name": _text(item.get("group_name"), 120)})
    out["operations"] = ops
    sup = cfg.get("supervisor") or {}
    sup_loc = str(sup.get("location_id") or "")
    if sup_loc and sup_loc not in location_ids:
        raise Invalid("supervisor", "La operación del supervisor no existe.")
    out["supervisor"] = {"name": _text(sup.get("name"), 120), "phone": clean_phone(sup.get("phone"), "supervisor"),
                         "email": clean_email(sup.get("email"), "supervisor"), "location_id": sup_loc}
    owners = []
    for item in (cfg.get("owners") or [])[:6]:
        item = item if isinstance(item, dict) else {}
        o = {"name": _text(item.get("name"), 120), "phone": clean_phone(item.get("phone"), "owners"), "email": clean_email(item.get("email"), "owners")}
        if o["name"] or o["phone"] or o["email"]:
            owners.append(o)
    out["owners"] = owners
    wl = str(cfg.get("weekly_location_id") or "")
    if wl and wl not in location_ids:
        raise Invalid("weekly_location_id", "Esa operación no existe en esta empresa.")
    out["weekly_location_id"] = wl
    out["weekly_weekday"] = clean_int(cfg.get("weekly_weekday"), "weekly_weekday", 0, 6)
    out["followup_time"] = clean_hhmm(cfg.get("followup_time"), "followup_time")
    for k in ("checkin_after_min", "checkout_after_min", "summary_after_min"):
        out[k] = clean_int(cfg.get(k), k, 0, 240)
    out["totals_weekday"] = clean_int(cfg.get("totals_weekday"), "totals_weekday", 0, 6)
    out["totals_time"] = clean_hhmm(cfg.get("totals_time"), "totals_time")
    tz = str(cfg.get("totals_tz") or "")
    if tz not in TIMEZONES:
        raise Invalid("totals_tz", "Zona horaria no válida.")
    out["totals_tz"] = tz
    kinds = cfg.get("kinds") if isinstance(cfg.get("kinds"), dict) else {}
    out["kinds"] = {k: kinds.get(k) is not False for k in KINDS}
    folders = cfg.get("drive_folders") if isinstance(cfg.get("drive_folders"), dict) else {}
    out["drive_folders"] = {str(k)[:60]: str(v)[:120] for k, v in folders.items()
                            if (str(k) in location_ids or k == "_other") and re.fullmatch(r"[\w-]{10,120}", str(v or ""))}
    return out


def due(at: datetime, now: datetime, window: timedelta = CUT_WINDOW) -> bool:
    return at <= now < at + window


def slot_window(slot: dict, day: date, tz_name: Any, after_in: int, after_out: int, anyone_started: bool) -> Optional[dict]:
    """Horas de una franja en un dia. Sin horario programado ese dia (fin de semana, dia libre):
    solo si alguien de la franja inicio turno, con las horas de siempre de la franja."""
    plan = ws.day_plan(slot, day)
    scheduled = plan is not None
    if not scheduled:
        if not anyone_started:
            return None
        plan = {"start": slot.get("start"), "end": slot.get("end")}
    start, end = ws.parse_hhmm(plan.get("start")), ws.parse_hhmm(plan.get("end"))
    if start is None or end is None:
        return None
    tz = ws.zone(tz_name)
    start_at = datetime.combine(day, start, tz)
    end_at = datetime.combine(day, end, tz)
    if end <= start:
        end_at += timedelta(days=1)
    return {"start": start_at.astimezone(timezone.utc), "end": end_at.astimezone(timezone.utc),
            "checkin_at": (start_at + timedelta(minutes=after_in)).astimezone(timezone.utc),
            "checkout_at": (end_at + timedelta(minutes=after_out)).astimezone(timezone.utc), "scheduled": scheduled}


def last_saturday(day: date) -> date:
    """El sabado de la ultima semana COMPLETA (domingo a sabado) antes de `day`."""
    return day - timedelta(days=((day.weekday() - 5) % 7) or 7)


def cut_title(company: str, op_name: str, slot_name: Optional[str], kind: str) -> str:
    parts = [company or "Clonexa", op_name] + ([slot_name] if slot_name else []) + ["Entrada" if kind == "checkin" else "Salida"]
    return "*" + " · ".join(parts) + "*"


def cut_when(day: date, at: datetime, tz_name: Any) -> str:
    return f"{day_es(day)} · {ws.local_clock(at, tz_name)} {us_time.abbr(tz_name, at)}"


def checkin_text(title: str, when: str, connected: list[tuple[str, bool]], missing: list[str]) -> str:
    """Pie de foto (y respaldo en texto) del corte de entrada: los que faltan en lista; los conectados solo el numero."""
    lines = [title, when, ""]
    if missing:
        lines += [f"❌ *Sin conectar / Not connected ({len(missing)}):*", numbered(missing), ""]
    else:
        lines += ["🎉 *Todos conectados / Everyone is clocked in*", ""]
    lines.append(f"✅ Conectados / Connected: {len(connected)} de {len(connected) + len(missing)}")
    paused = sum(1 for _, p in connected if p)
    if paused:
        lines.append(f"⏸️ En pausa / On break: {paused}")
    return "\n".join(lines)


def checkout_text(title: str, when: str, done: list[str], still: list[tuple[str, int]]) -> str:
    lines = [title, when, ""]
    if still:
        lines += [f"⚠️ *Siguen conectados / Still clocked in ({len(still)}):*",
                  numbered([f"{n} · {hm(m)}{' 🔴' if m > LONG_SHIFT_MIN else ''}" for n, m in still]), ""]
    else:
        lines += ["🎉 *Todos cerraron / Everyone clocked out*", ""]
    lines.append(f"✅ Ya cerraron / Clocked out: {len(done)} de {len(done) + len(still)}")
    return "\n".join(lines)


def cut_message(kind: str, company: str, op: dict, slot_name: Optional[str], day: date, win: dict, lists: dict) -> tuple[str, dict]:
    """(pie de foto, adjunto de la tarjeta). La tarjeta guarda sus datos: un reintento dibuja lo mismo."""
    at = win["checkin_at"] if kind == "checkin" else win["checkout_at"]
    abbr = us_time.abbr(op["tz"], at)
    title, when = cut_title(company, op["name"], slot_name, kind), cut_when(day, at, op["tz"])
    if kind == "checkin":
        caption = checkin_text(title, when, lists["connected"], lists["missing"])
        sub = f"{day_full(day)} · Entrada {ws.local_clock(win['start'], op['tz'])} {abbr} · Corte {ws.local_clock(at, op['tz'])}"
    else:
        caption = checkout_text(title, when, lists["done"], lists["still"])
        sub = f"{day_full(day)} · Salida {ws.local_clock(win['end'], op['tz'])} {abbr} · Corte {ws.local_clock(at, op['tz'])}"
    operation = op["name"] + (f" · {slot_name}" if slot_name else "")
    card = {"type": kind, "company": company or "VOLTAGE", "operation": operation, "subtitle": sub,
            "connected": [[n, bool(p)] for n, p in lists["connected"]], "missing": list(lists["missing"]),
            "done": list(lists["done"]), "still": [[n, int(m), hm(m)] for n, m in lists["still"]]}
    slug = re.sub(r"[^a-z0-9]+", "_", op["name"].lower()).strip("_") or "operacion"
    return caption, {"kind": "card_png", "mimetype": "image/png", "card": card,
                     "file_name": f"corte_{'entrada' if kind == 'checkin' else 'salida'}_{slug}_{day.isoformat()}.png"}


def timesheet_text(kind: str, company: str, op_name: str, day: date, email: str) -> str:
    """Corto y amable, con 📸: una linea en espanol y una en ingles."""
    mail = email or "el correo de Clonexa"
    mail_en = email or "the Clonexa email"
    if kind == "ts_weekly":
        return (f"📸 Hola equipo {op_name}: recuerden enviar la foto del timesheet de la semana a este WhatsApp o a {mail}. ¡Gracias!\n"
                f"📸 Hi {op_name} team: please send this week's timesheet photo here or to {mail_en}. Thanks!")
    if kind == "ts_followup":
        return (f"📸 Aún no llega el timesheet del {day_es(day)} ({op_name}). ¿Lo envían por aquí o a {mail}? ¡Gracias!\n"
                f"📸 We haven't received the {day_en(day)} timesheet ({op_name}) yet. Please send it here or to {mail_en}. Thanks!")
    return (f"📸 Hola, recuerda enviar la foto del timesheet de hoy ({op_name}) a este WhatsApp o a {mail}. ¡Gracias!\n"
            f"📸 Hi, please send today's timesheet photo ({op_name}) here or to {mail_en}. Thanks!")


AUTOREPLY_TEXT = ("Este número solo envía reportes de VOLTAGE. Para tu turno usa el bot de Telegram.\n"
                  "This number only sends VOLTAGE reports. Use the Telegram bot for your shift.")
RECEIVED_TEXT = "Recibida ✅ / Received ✅"


def sign(secret: str, payload: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).decode().rstrip("=")
    mac = hmac.new(f"{secret}:files".encode(), raw.encode(), hashlib.sha256).hexdigest()[:40]
    return f"{raw}.{mac}"


def unsign(secret: str, token: str, now: Optional[datetime] = None) -> Optional[dict]:
    if not secret or "." not in str(token or ""):
        return None
    raw, mac = str(token).rsplit(".", 1)
    good = hmac.new(f"{secret}:files".encode(), raw.encode(), hashlib.sha256).hexdigest()[:40]
    if not hmac.compare_digest(good, mac):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, TypeError):
        return None
    now = now or datetime.now(timezone.utc)
    if not isinstance(data, dict) or float(data.get("exp") or 0) < now.timestamp():
        return None
    return data


def secret_ok(header_value: Any) -> bool:
    secret = os.getenv(ENV_SECRET) or ""
    return bool(secret) and hmac.compare_digest(str(header_value or ""), secret)


# ------------------------------------------------------------------ interruptor y configuracion
async def is_on(db: Optional[AsyncSession], company_id: Any) -> bool:
    """Nunca falla: ante cualquier error, apagado."""
    if db is None or not company_id:
        return False
    try:
        raw = (await db.execute(text("""
            SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = CAST(:c AS uuid) AND lower(m.code) = :m AND COALESCE(cm.enabled, true) IS TRUE
            LIMIT 1
        """), {"c": str(company_id), "m": MODULE})).scalar()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        return False
    return ws.settings_dict(raw).get(KEY) is True


async def companies_on(db: AsyncSession) -> list[str]:
    rows = (await db.execute(text("""
        SELECT cm.company_id::text FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE lower(m.code) = :m AND COALESCE(cm.enabled, true) IS TRUE AND (cm.settings::jsonb ->> :k) = 'true'
    """), {"m": MODULE, "k": KEY})).all()
    return [str(r[0]) for r in rows]


async def get_config(db: AsyncSession, company_id: Any) -> dict:
    raw = (await db.execute(text("SELECT config FROM wa_report_config WHERE company_id = CAST(:c AS uuid)"),
                            {"c": str(company_id)})).scalar()
    return merge_config(raw)


async def save_config(db: AsyncSession, company_id: Any, body: Any, *, actor: str) -> dict:
    locs = {loc["id"] for loc in await locations(db, company_id)}
    cfg = clean_config(body, locs)
    await db.execute(text("""
        INSERT INTO wa_report_config (company_id, config, updated_by, updated_at)
        VALUES (CAST(:c AS uuid), CAST(:j AS jsonb), :by, now())
        ON CONFLICT (company_id) DO UPDATE SET config = EXCLUDED.config, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"c": str(company_id), "j": json.dumps(cfg), "by": str(actor or "")[:200] or None})
    await db.commit()
    return cfg


async def locations(db: AsyncSession, company_id: Any) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, name, timezone FROM work_locations WHERE company_id = CAST(:c AS uuid) ORDER BY name
    """), {"c": str(company_id)})).mappings().all()
    return [dict(r) for r in rows]


async def company_name(db: AsyncSession, company_id: Any) -> str:
    return str((await db.execute(text("SELECT name FROM companies WHERE id = CAST(:c AS uuid)"), {"c": str(company_id)})).scalar() or "")


async def operations(db: AsyncSession, company_id: Any, cfg: dict) -> list[dict]:
    places = {p["id"]: p for p in await locations(db, company_id)}
    out = []
    for item in cfg.get("operations") or []:
        place = places.get(str(item.get("location_id")))
        if place:
            out.append({"id": place["id"], "name": str(place["name"] or "").strip(), "tz": place["timezone"] or "America/New_York",
                        "group_jid": item.get("group_jid") or "", "group_name": item.get("group_name") or ""})
    return out


async def people(db: AsyncSession, company_id: Any, location_ids: list[str]) -> list[dict]:
    """Personal activo de esas operaciones con su horario (sin directores ni dueños)."""
    if not location_ids:
        return []
    rows = (await db.execute(text("""
        SELECT e.id::text AS id, COALESCE(e.full_name, '') AS name, COALESCE(e.role, '') AS role,
               e.work_location_id::text AS location_id, COALESCE(s.slot, 1) AS slot
        FROM employees e LEFT JOIN employee_schedule_slots s ON s.company_id = e.company_id AND s.employee_id = e.id
        WHERE e.company_id = CAST(:c AS uuid) AND e.work_location_id::text = ANY(:l)
          AND lower(COALESCE(e.status, 'active')) IN ('active', 'activo')
    """), {"c": str(company_id), "l": list(location_ids)})).mappings().all()
    out = []
    for r in rows:
        role = str(r["role"] or "").strip().lower()
        if role in EXCLUDED_ROLES:
            continue
        out.append({"id": r["id"], "name": clean_name(r["name"]), "location_id": r["location_id"], "slot": int(r["slot"] or 1)})
    out.sort(key=lambda p: p["name"].lower())
    return out


def _shifts_by_person(data: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for s in data.get("shifts") or []:
        out.setdefault(s["employee_id"], []).append({"start": s["start"], "end": s.get("end"), "paused": False})
    for s in data.get("open_shifts") or []:
        pause = s.get("pause_open") or {}
        out.setdefault(s["employee_id"], []).append({"start": s["start"], "end": None, "paused": bool(pause),
                                                     "breaks": list(s.get("breaks") or []), "pause_since": pause.get("occurred_at")})
    return out


def in_progress_minutes(item: dict, now: datetime) -> int:
    """Minutos trabajados de un turno abierto hasta ahora (sin sus pausas)."""
    total = (now - item["start"]).total_seconds()
    for a, b in item.get("breaks") or []:
        if a and b:
            total -= (b - a).total_seconds()
    if item.get("pause_since"):
        total -= max(0.0, (now - item["pause_since"]).total_seconds())
    return max(0, int(total // 60))


def started_on(items: list[dict], day: date, tz_name: Any, until: datetime) -> list[dict]:
    tz = ws.zone(tz_name)
    return [s for s in items if s["start"] <= until and s["start"].astimezone(tz).date() == day]


def cut_lists(kind: str, members: list[dict], shifts: dict[str, list[dict]], day: date, tz_name: Any, now: datetime) -> dict:
    """Las listas de un corte. Entrada: conectados (⏸ si esta en pausa) y no conectados.
    Salida: ya cerraron y siguen conectados (con las horas abiertas)."""
    connected, missing, done, still = [], [], [], []
    for p in members:
        today = started_on(shifts.get(p["id"]) or [], day, tz_name, now)
        if not today:
            missing.append(p["name"])
            continue
        open_ = [s for s in today if s["end"] is None]
        connected.append((p["name"], bool(open_ and open_[-1]["paused"])))
        if open_:
            still.append((p["name"], int((now - open_[-1]["start"]).total_seconds() // 60)))
        else:
            done.append(p["name"])
    return {"connected": connected, "missing": missing, "done": done, "still": still}


# ------------------------------------------------------------------ destinos
def recipients(cfg: dict, who: str, op: Optional[dict] = None, *, force_test: bool = False) -> list[dict]:
    """Destinos de un aviso, ya resueltos para el modo prueba. who: group | supervisor | owners."""
    test = force_test or cfg.get("test_mode") is not False
    out: list[dict] = []
    if who == "group" and op:
        out.append({"channel": "whatsapp", "destination": f"Grupo {op['name']}", "target": op.get("group_jid") or "", "audience": "group"})
    elif who == "supervisor":
        sup = cfg.get("supervisor") or {}
        out.append({"channel": "whatsapp", "destination": f"Supervisor {sup.get('name') or ''}".strip(), "target": sup.get("phone") or ""})
    elif who == "owners":
        for o in cfg.get("owners") or []:
            if o.get("phone"):
                out.append({"channel": "whatsapp", "destination": f"Dueño {o.get('name') or ''}".strip(), "target": o["phone"]})
        mails = [o["email"] for o in cfg.get("owners") or [] if o.get("email")]
        out.append({"channel": "email", "destination": "Correo dueños", "target": ",".join(mails)})
    if test:
        for r in out:
            r["destination"] = f"{r['destination']} → prueba"[:200]
            r["target"] = (cfg.get("own_number") or "") if r["channel"] == "whatsapp" else (cfg.get("clonexa_email") or "")
    for r in out:
        r["test"] = test
    return out


# ------------------------------------------------------------------ avisos (reclamo atomico)
async def exists(db: AsyncSession, cid: str, key: str) -> bool:
    return bool((await db.execute(text("SELECT 1 FROM wa_report_notices WHERE company_id = CAST(:c AS uuid) AND dedupe_key = :k"),
                                  {"c": cid, "k": key})).first())


def is_group_delivery(d: dict) -> bool:
    return d.get("audience") == "group" or str(d.get("target") or "").endswith("@g.us")


async def claim(db: AsyncSession, cid: str, key: str, kind: str, *, location_id: Optional[str], day: Optional[date], slot: int,
                deliveries: list[dict], test: bool = False) -> Optional[int]:
    """Crea el aviso y sus envios en UNA transaccion. None si ya existia (otra copia o antes del reinicio)."""
    nid = (await db.execute(text("""
        INSERT INTO wa_report_notices (company_id, dedupe_key, kind, location_id, local_date, slot, test)
        VALUES (CAST(:c AS uuid), :k, :kind, CAST(:l AS uuid), :d, :s, :t)
        ON CONFLICT (company_id, dedupe_key) DO NOTHING RETURNING id
    """), {"c": cid, "k": key[:160], "kind": kind, "l": location_id or None, "d": day, "s": slot, "t": test})).scalar()
    if nid is None:
        await db.rollback()
        return None
    # 074A: candado final. Un envio a grupo de un tipo que no es corte ni timesheet no se crea nunca.
    deliveries = [d for d in deliveries if not is_group_delivery(d) or kind in GROUP_KINDS]
    for d in deliveries:
        missing = not d.get("target")
        await db.execute(text("""
            INSERT INTO wa_report_deliveries (notice_id, company_id, kind, channel, destination, target, subject, body, attachments, test,
                                              status, last_error, next_attempt_at)
            VALUES (:n, CAST(:c AS uuid), :kind, :ch, :dest, :tg, :subj, :body, CAST(:att AS jsonb), :t, :st, :err, to_timestamp(0))
        """), {"n": nid, "c": cid, "kind": kind, "ch": d["channel"], "dest": str(d.get("destination") or "")[:200], "tg": str(d.get("target") or "")[:400],
               "subj": (str(d["subject"])[:300] if d.get("subject") else None), "body": d.get("body") or "", "att": json.dumps(d.get("attachments") or []),
               "t": bool(d.get("test")), "st": d.get("status") or ("skipped" if missing else "pending"),
               "err": "Sin destino configurado" if missing and not d.get("status") else None})
    await db.commit()
    return int(nid)


def _deliveries(targets: list[dict], body: str, *, subject: Optional[str] = None, attachments: Optional[list] = None,
                email_body: Optional[str] = None, wa_attachments: Optional[list] = None) -> list[dict]:
    out = []
    for r in targets:
        prefix = TEST_PREFIX if r.get("test") else ""
        if r["channel"] == "email":
            mail = email_body or body
            if mail.startswith(HTML_MARK):
                banner = '<p style="background:#fef3c7;padding:6px 10px;border-radius:6px"><b>[PRUEBA]</b></p>' if prefix else ""
                mail = HTML_MARK + banner + mail[len(HTML_MARK):]
            else:
                mail = prefix + mail
            out.append({**r, "subject": prefix + (subject or "Clonexa"), "body": mail, "attachments": attachments or []})
        else:
            out.append({**r, "body": prefix + body, "attachments": list(wa_attachments or [])})
    return out


# ------------------------------------------------------------------ resumenes (mismas horas que Nomina)
async def _snapshot(db: AsyncSession, cid: str, start: date, end: date) -> dict:
    from uuid import UUID

    from app.api.v1.endpoints.payroll import calculate_period_snapshot

    return await calculate_period_snapshot(db, UUID(cid), start, end)


def _op_rows(snap: dict, op_name: str) -> list[dict]:
    return [r for r in snap.get("rows") or [] if ((r.get("us") or {}).get("place") or "") == op_name]


def _esc(value: Any) -> str:
    import html

    return html.escape(str(value if value is not None else ""))


def _html(title: str, sub: str, blocks: list[str], foot: str) -> str:
    return (HTML_MARK + '<div style="font-family:Arial,Helvetica,sans-serif;color:#0f172a;max-width:680px">'
            f'<h2 style="margin:0 0 4px">{_esc(title)}</h2><p style="margin:0 0 16px;color:#475569">{_esc(sub)}</p>'
            + "".join(blocks) + f'<p style="color:#475569;margin-top:18px">{_esc(foot)}</p></div>')


def _table(head: list[str], rows: list[list[Any]], highlight: Optional[list[bool]] = None) -> str:
    th = "".join(f'<th style="text-align:left;padding:6px 8px;border-bottom:2px solid #cbd5e1">{_esc(h)}</th>' for h in head)
    body = ""
    for i, row in enumerate(rows):
        bg = ' style="background:#fef3c7"' if highlight and highlight[i] else ""
        body += f"<tr{bg}>" + "".join(f'<td style="padding:6px 8px;border-bottom:1px solid #e2e8f0">{_esc(c)}</td>' for c in row) + "</tr>"
    return f'<table style="border-collapse:collapse;width:100%;font-size:14px;margin:8px 0 18px"><tr>{th}</tr>{body}</table>'


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


async def owners_daily(db: AsyncSession, cid: str, company: str, day: date, ops: list[dict], now: datetime) -> dict:
    snap = await _snapshot(db, cid, day, day)
    data = await _load(db, cid, now)
    shifts = _shifts_by_person(data)
    persons = await people(db, cid, [o["id"] for o in ops])
    name = company or "Clonexa"
    lines = [f"📊 *{name} · Resumen del día*", f"{day_full(day)} · Daily summary"]
    table = []
    total_people = total_min = total_open = total_acc = 0
    for op in ops:
        rows = _op_rows(snap, op["name"])
        worked = {str(r["employee_id"]) for r in rows}
        open_items: dict[str, dict] = {}
        for p in [p for p in persons if p["location_id"] == op["id"]]:
            for item in shifts.get(p["id"]) or []:
                if item["end"] is None:
                    open_items[p["id"]] = item
                if item["start"].astimezone(ws.zone(op["tz"])).date() == day:
                    worked.add(p["id"])
        worked |= set(open_items)
        held = [u for u in snap.get("unverified_shifts") or [] if (u.get("place") or "") == op["name"]]
        minutes = sum(int((r.get("us") or {}).get("payable_minutes") or 0) for r in rows)
        acc = sum(in_progress_minutes(item, now) for item in open_items.values())
        n_open = len(open_items)
        total_people, total_min, total_open, total_acc = total_people + len(worked), total_min + minutes, total_open + n_open, total_acc + acc
        abbr = us_time.abbr(op["tz"], now)
        lines += ["", f"📍 *{op['name']} ({abbr})*", f"👥 {len(worked)} personas · ⏱️ {hm(minutes)} cerradas"]
        if n_open:
            lines.append(f"🔄 {n_open} en curso ({hm(acc)} acumuladas)")
            lines.append(f"⚠️ {n_open} {_plural(n_open, 'turno sigue abierto', 'turnos siguen abiertos')}")
        if held:
            lines.append(f"🕓 {len(held)} por confirmar")
        table.append([f"{op['name']} ({abbr})", len(worked), hm(minutes), n_open, hm(acc), len(held)])
    lines += ["", RULE, f"*Total:* {total_people} personas · {hm(total_min)} cerradas"
              + (f" · 🔄 {total_open} en curso ({hm(total_acc)})" if total_open else ""),
              "📎 Planilla en PDF en tu correo / PDF timesheet sent by email"]
    html = _html(f"{name} · Resumen del día", f"{day_full(day)} · Daily summary",
                 [_table(["Operación", "Personas", "Horas cerradas", "En curso", "Acumuladas en curso", "Por confirmar"],
                         table + [["Total", total_people, hm(total_min), total_open, hm(total_acc), ""]],
                         [bool(r[3]) for r in table] + [False])],
                 "La planilla del día (entrada, salida, pausas y horas por persona) va en el PDF adjunto. / The daily timesheet is attached as PDF.")
    return {"body": "\n".join(lines), "html": html, "subject": f"{name} · Planilla del día / Daily timesheet · {day.isoformat()}",
            "attachments": [{"kind": "daily_pdf", "from": day.isoformat(), "to": day.isoformat(),
                             "file_name": f"planilla_{day.isoformat()}.pdf", "mimetype": "application/pdf"}]}


def hours_round(minutes: Any) -> str:
    """1.240 h: horas enteras con punto de miles (mensaje corto de la semana)."""
    return f"{int(round(int(minutes or 0) / 60)):,}".replace(",", ".") + " h"


async def weekly_totals(db: AsyncSession, cid: str, company: str, sunday: date, ops: list[dict]) -> dict:
    """074A: a los dueños UN mensaje corto (por operacion: personas, horas y extra; top 3 de extras);
    el detalle por persona va solo en el correo (tabla, PDF y Excel). Nada para los grupos."""
    saturday = sunday + timedelta(days=6)
    snap = await _snapshot(db, cid, sunday, saturday)
    span = f"{sunday.day:02d}/{sunday.month:02d} – {saturday.day:02d}/{saturday.month:02d}"
    name = company or "Clonexa"
    owner = [f"📊 *{name} · Semana {span}*"]
    blocks: list[str] = []
    all_reg = all_ot = all_people = 0
    extras: list[tuple[int, str]] = []
    for op in ops:
        rows = sorted(_op_rows(snap, op["name"]), key=lambda r: clean_name(r.get("employee_name")).lower())
        reg = sum(int(r["us"].get("regular_minutes") or 0) for r in rows)
        ot = sum(int(r["us"].get("overtime_minutes") or 0) for r in rows)
        all_reg, all_ot, all_people = all_reg + reg, all_ot + ot, all_people + len(rows)
        owner.append(f"📍 {op['name']}: {len(rows)} {_plural(len(rows), 'persona', 'personas')} · {hours_round(reg + ot)} ({hours_round(ot)} extra)")
        extras += [(int(r["us"].get("overtime_minutes") or 0), clean_name(r.get("employee_name"))) for r in rows
                   if int(r["us"].get("overtime_minutes") or 0) > 0]
        blocks.append(f'<h3 style="margin:14px 0 4px">{_esc(op["name"])} · {len(rows)} personas · {_esc(hm(reg + ot))}</h3>'
                      + _table(["#", "Persona", "Total", "Regulares", "Extra"],
                               [[i, clean_name(r.get("employee_name")), hm(r["us"].get("payable_minutes")), hm(r["us"].get("regular_minutes")),
                                 hm(r["us"].get("overtime_minutes"))] for i, r in enumerate(rows, 1)],
                               [int(r["us"].get("overtime_minutes") or 0) > 0 for r in rows]))
    top = sorted(extras, key=lambda x: (-x[0], x[1].lower()))[:3]
    owner.append("⚠️ Más horas extra: " + ", ".join(f"{n} {hm(m)}" for m, n in top) if top else "✅ Sin horas extra / No overtime")
    owner.append("📎 Detalle por persona en PDF y Excel en tu correo / Details by person in your email")
    html = _html(f"{name} · Totales de la semana", f"{span} · Weekly totals (domingo a sábado, FLSA: extra sobre 40 h)", blocks,
                 f"Total: {all_people} personas · {hm(all_reg + all_ot)} ({hm(all_reg)} regulares + {hm(all_ot)} extra). PDF y Excel adjuntos.")
    attachments = [{"kind": "weekly_pdf", "from": sunday.isoformat(), "to": saturday.isoformat(),
                    "file_name": f"semana_{sunday.isoformat()}_{saturday.isoformat()}.pdf", "mimetype": "application/pdf"},
                   {"kind": "weekly_xlsx", "from": sunday.isoformat(), "to": saturday.isoformat(),
                    "file_name": f"semana_{sunday.isoformat()}_{saturday.isoformat()}.xlsx",
                    "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}]
    return {"owner": "\n".join(owner), "html": html, "attachments": attachments,
            "subject": f"{name} · Totales de la semana / Weekly totals · {sunday.isoformat()} – {saturday.isoformat()}"}


def build_xlsx(snap: dict, company: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    sheet = wb.active
    sheet.title = "Semana"
    period = snap.get("period") or {}
    sheet.append([f"{company} · {period.get('period_start')} – {period.get('period_end')} · horas (FLSA: extra sobre 40 h por semana)"])
    sheet.append([])
    head = ["Operación", "Persona", "Rol", "Días", "Horas pagables", "Regulares", "Extra (overtime)", "Pausas", "Minutos pagables", "Minutos regulares", "Minutos extra"]
    sheet.append(head)
    for cell in sheet[3]:
        cell.font = Font(bold=True)
    rows = sorted(snap.get("rows") or [], key=lambda r: (str((r.get("us") or {}).get("place") or "~"), str(r.get("employee_name") or "").lower()))
    for r in rows:
        us = r.get("us") or {}
        sheet.append([us.get("place") or "Sin lugar asignado", clean_name(r.get("employee_name")), r.get("employee_role") or "", us.get("days_worked") or 0,
                      hm(us.get("payable_minutes")), hm(us.get("regular_minutes")), hm(us.get("overtime_minutes")), hm(us.get("pause_minutes")),
                      int(us.get("payable_minutes") or 0), int(us.get("regular_minutes") or 0), int(us.get("overtime_minutes") or 0)])
    for col, width in zip("ABCDEFGHIJK", (18, 32, 14, 6, 14, 14, 16, 12, 10, 10, 10)):
        sheet.column_dimensions[col].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def render_file(db: AsyncSession, cid: str, spec: dict) -> tuple[bytes, str, str]:
    from app.services import us_payroll_export

    if spec.get("kind") == "card_png":
        from app.services import group_reports_card

        row = (await db.execute(text("""
            SELECT attachments FROM wa_report_deliveries WHERE company_id = CAST(:c AS uuid) AND id = :d
        """), {"c": cid, "d": int(spec.get("d") or 0)})).first()
        items = ws._json(row[0], []) if row else []
        index = int(spec.get("i") or 0)
        att = items[index] if 0 <= index < len(items) else None
        if not att or att.get("kind") != "card_png":
            raise LookupError("Tarjeta no encontrada")
        png, _layout = group_reports_card.render(att["card"])
        return png, att.get("file_name") or "corte.png", "image/png"

    start, end = date.fromisoformat(spec["from"]), date.fromisoformat(spec["to"])
    snap = await _snapshot(db, cid, start, end)
    name = await company_name(db, cid)
    if spec.get("kind") == "weekly_xlsx":
        return build_xlsx(snap, name), f"semana_{start}_{end}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    prefix = "planilla" if spec.get("kind") == "daily_pdf" else "semana"
    return us_payroll_export.build_pdf(snap, name), f"{prefix}_{start}_{end}.pdf", "application/pdf"


async def _load(db: AsyncSession, cid: str, now: datetime) -> dict:
    from app.services import us_payroll

    return await us_payroll.load(db, cid, now - timedelta(days=2), now)


# ------------------------------------------------------------------ planificador
async def _receipt_since(db: AsyncSession, cid: str, location_id: str, since: datetime) -> bool:
    return bool((await db.execute(text("""
        SELECT 1 FROM wa_timesheet_receipts WHERE company_id = CAST(:c AS uuid) AND location_id = CAST(:l AS uuid) AND received_at >= :s LIMIT 1
    """), {"c": cid, "l": location_id, "s": since})).first())


async def _notice_on(db: AsyncSession, cid: str, kind: str, location_id: str, day: date) -> bool:
    return bool((await db.execute(text("""
        SELECT 1 FROM wa_report_notices WHERE company_id = CAST(:c AS uuid) AND kind = :k AND location_id = CAST(:l AS uuid)
          AND local_date = :d AND test IS FALSE LIMIT 1
    """), {"c": cid, "k": kind, "l": location_id, "d": day})).first())


async def plan_company(db: AsyncSession, company_id: Any, now: Optional[datetime] = None) -> dict:
    """Una pasada: crea los avisos que tocan (sin enviarlos). Devuelve lo creado por tipo."""
    now = now or datetime.now(timezone.utc)
    cid = str(company_id)
    cfg = await get_config(db, cid)
    kinds = cfg["kinds"]
    ops = await operations(db, cid, cfg)
    stats = {k: 0 for k in KINDS}
    if not ops:
        return stats
    company = await company_name(db, cid)
    persons = await people(db, cid, [o["id"] for o in ops])
    data = await _load(db, cid, now)
    shifts = _shifts_by_person(data)
    last_exit: dict[date, datetime] = {}

    for op in ops:
        tz = ws.zone(op["tz"])
        local_today = now.astimezone(tz).date()
        for day in (local_today - timedelta(days=1), local_today):
            week = await ws.week(db, cid, op["id"], ws.week_start(day))
            if not week["configured"]:
                continue
            many = len(week["slots"]) > 1
            op_exit: Optional[datetime] = None
            for slot in week["slots"]:
                number = int(slot.get("slot") or 1)
                members = [p for p in persons if p["location_id"] == op["id"] and int(ws.slot_of(week["slots"], p["slot"]).get("slot") or 1) == number]
                anyone = any(started_on(shifts.get(p["id"]) or [], day, op["tz"], now) for p in members)
                win = slot_window(slot, day, op["tz"], int(cfg["checkin_after_min"]), int(cfg["checkout_after_min"]), anyone)
                if not win:
                    continue
                op_exit = max(op_exit, win["end"]) if op_exit else win["end"]
                slot_name = slot.get("name") if many else None
                for kind, at in (("checkin", win["checkin_at"]), ("checkout", win["checkout_at"])):
                    key = f"{kind}:{op['id']}:{day.isoformat()}:{number}"
                    if not kinds.get(kind) or not due(at, now) or await exists(db, cid, key):
                        continue
                    lists = cut_lists(kind, members, shifts, day, op["tz"], now)
                    caption, card = cut_message(kind, company, op, slot_name, day, win, lists)
                    if await claim(db, cid, key, kind, location_id=op["id"], day=day, slot=number,
                                   deliveries=_deliveries(recipients(cfg, "group", op), caption, wa_attachments=[card])):
                        stats[kind] += 1
            if op_exit is None:
                continue
            last_exit[day] = max(last_exit.get(day, op_exit), op_exit)
            reminder_at = op_exit + timedelta(minutes=int(cfg["checkout_after_min"]))
            sup = cfg.get("supervisor") or {}
            plan = []
            if kinds.get("ts_daily") and sup.get("location_id") == op["id"]:
                plan.append(("ts_daily", "supervisor"))
            if kinds.get("ts_weekly") and cfg.get("weekly_location_id") == op["id"] and day.weekday() == int(cfg["weekly_weekday"]):
                plan.append(("ts_weekly", "group"))
            for kind, who in plan:
                key = f"{kind}:{op['id']}:{day.isoformat()}"
                if not due(reminder_at, now) or await exists(db, cid, key):
                    continue
                body = timesheet_text(kind, company, op["name"], day, cfg.get("clonexa_email") or "")
                if await claim(db, cid, key, kind, location_id=op["id"], day=day, slot=0,
                               deliveries=_deliveries(recipients(cfg, who, op), body)):
                    stats[kind] += 1

        # 9:00 del dia siguiente: un solo recordatorio mas si no llego la foto
        if kinds.get("ts_followup"):
            yesterday = local_today - timedelta(days=1)
            follow_at = datetime.combine(local_today, ws.parse_hhmm(cfg["followup_time"]), tz).astimezone(timezone.utc)
            for original, who in (("ts_daily", "supervisor"), ("ts_weekly", "group")):
                key = f"ts_followup:{original}:{op['id']}:{yesterday.isoformat()}"
                if not due(follow_at, now) or await exists(db, cid, key) or not await _notice_on(db, cid, original, op["id"], yesterday):
                    continue
                since = datetime.combine(yesterday, time(0, 0), tz).astimezone(timezone.utc)
                if await _receipt_since(db, cid, op["id"], since):
                    continue
                body = timesheet_text("ts_followup", company, op["name"], yesterday, cfg.get("clonexa_email") or "")
                if await claim(db, cid, key, "ts_followup", location_id=op["id"], day=yesterday, slot=0,
                               deliveries=_deliveries(recipients(cfg, who, op), body)):
                    stats["ts_followup"] += 1

    # Dueños: 30 min despues de la ULTIMA salida del dia (todas las operaciones)
    if kinds.get("owners_daily"):
        for day, exit_at in sorted(last_exit.items()):
            key = f"owners_daily:{day.isoformat()}"
            if not due(exit_at + timedelta(minutes=int(cfg["summary_after_min"])), now) or await exists(db, cid, key):
                continue
            s = await owners_daily(db, cid, company, day, ops, now)
            if await claim(db, cid, key, "owners_daily", location_id=None, day=day, slot=0,
                           deliveries=_deliveries(recipients(cfg, "owners"), s["body"], subject=s["subject"], attachments=s["attachments"],
                                                  email_body=s["html"])):
                stats["owners_daily"] += 1

    # Totales de la semana (domingo a sabado), lunes 8:00 ET
    if kinds.get("weekly_totals"):
        wtz = ws.zone(cfg["totals_tz"])
        local = now.astimezone(wtz)
        if local.weekday() == int(cfg["totals_weekday"]):
            at = datetime.combine(local.date(), ws.parse_hhmm(cfg["totals_time"]), wtz).astimezone(timezone.utc)
            saturday = last_saturday(local.date())
            sunday = saturday - timedelta(days=6)
            key = f"weekly_totals:{sunday.isoformat()}"
            if due(at, now, WEEKLY_WINDOW) and not await exists(db, cid, key):
                w = await weekly_totals(db, cid, company, sunday, ops)
                deliveries = _deliveries(recipients(cfg, "owners"), w["owner"], subject=w["subject"], attachments=w["attachments"], email_body=w["html"])
                if await claim(db, cid, key, "weekly_totals", location_id=None, day=sunday, slot=0, deliveries=deliveries):
                    stats["weekly_totals"] += 1
    return stats


# ------------------------------------------------------------------ "Enviar prueba ahora"
async def send_test(db: AsyncSession, company_id: Any, kind: str, location_id: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """Arma el aviso con los datos de hoy y lo manda SIEMPRE en modo prueba (a mi numero / correo de
    Clonexa), sin importar el modo y sin contar como el aviso real del dia."""
    if kind not in KINDS:
        raise Invalid("kind", "Tipo de aviso no válido.")
    now = now or datetime.now(timezone.utc)
    cid = str(company_id)
    cfg = await get_config(db, cid)
    ops = await operations(db, cid, cfg)
    if not ops:
        raise Invalid("operations", "Agrega al menos una operación en la configuración.")
    op = next((o for o in ops if o["id"] == str(location_id or "")), None)
    if op is None:
        wanted = {"ts_daily": (cfg.get("supervisor") or {}).get("location_id"), "ts_weekly": cfg.get("weekly_location_id")}.get(kind)
        op = next((o for o in ops if o["id"] == wanted), ops[0])
    company = await company_name(db, cid)
    day = now.astimezone(ws.zone(op["tz"])).date()
    if kind in ("checkin", "checkout"):
        week = await ws.week(db, cid, op["id"], ws.week_start(day))
        if not week["configured"]:
            raise Invalid("schedule", f"{op['name']} no tiene Horario de la semana guardado.")
        slot = week["slots"][0]
        persons = [p for p in await people(db, cid, [op["id"]]) if int(ws.slot_of(week["slots"], p["slot"]).get("slot") or 1) == int(slot.get("slot") or 1)]
        shifts = _shifts_by_person(await _load(db, cid, now))
        win = slot_window(slot, day, op["tz"], int(cfg["checkin_after_min"]), int(cfg["checkout_after_min"]), True)
        lists = cut_lists(kind, persons, shifts, day, op["tz"], now)
        caption, card = cut_message(kind, company, op, slot.get("name") if len(week["slots"]) > 1 else None, day, win, lists)
        deliveries = _deliveries(recipients(cfg, "group", op, force_test=True), caption, wa_attachments=[card])
    elif kind in ("ts_daily", "ts_weekly", "ts_followup"):
        who = "supervisor" if kind == "ts_daily" else "group"
        deliveries = _deliveries(recipients(cfg, who, op, force_test=True), timesheet_text(kind, company, op["name"], day, cfg.get("clonexa_email") or ""))
    elif kind == "owners_daily":
        s = await owners_daily(db, cid, company, day, ops, now)
        deliveries = _deliveries(recipients(cfg, "owners", force_test=True), s["body"], subject=s["subject"], attachments=s["attachments"],
                                 email_body=s["html"])
    else:
        saturday = last_saturday(now.astimezone(ws.zone(cfg["totals_tz"])).date())
        w = await weekly_totals(db, cid, company, saturday - timedelta(days=6), ops)
        deliveries = _deliveries(recipients(cfg, "owners", force_test=True), w["owner"], subject=w["subject"], attachments=w["attachments"],
                                 email_body=w["html"])
    nid = await claim(db, cid, f"test:{kind}:{uuid.uuid4().hex}", kind, location_id=op["id"] if kind not in ("owners_daily", "weekly_totals") else None,
                      day=day, slot=0, deliveries=deliveries, test=True)
    return {"notice_id": nid, "deliveries": len(deliveries)}


# ------------------------------------------------------------------ envio a n8n
async def _take(db: AsyncSession, cid: str, now: datetime) -> Optional[dict]:
    row = (await db.execute(text("""
        UPDATE wa_report_deliveries SET status = 'sending', attempts = attempts + 1, next_attempt_at = :lease
         WHERE id = (SELECT id FROM wa_report_deliveries
                      WHERE company_id = CAST(:c AS uuid) AND status IN ('pending', 'sending') AND next_attempt_at <= :now
                        AND attempts < :max
                      ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED)
        RETURNING id, notice_id, kind, channel, destination, target, subject, body, attachments, test, attempts
    """), {"c": cid, "now": now, "lease": now + timedelta(minutes=5), "max": MAX_ATTEMPTS})).mappings().first()
    await db.commit()
    return dict(row) if row else None


async def _finish(db: AsyncSession, row: dict, ok: bool, error: Optional[str], now: datetime) -> None:
    if ok:
        status, next_at = "sent", now
    elif int(row["attempts"]) >= MAX_ATTEMPTS:
        status, next_at = "failed", now
    else:
        status, next_at = "pending", now + RETRY_AFTER[min(int(row["attempts"]) - 1, len(RETRY_AFTER) - 1)]
    await db.execute(text("""
        UPDATE wa_report_deliveries SET status = :s, next_attempt_at = :n, last_error = :e, sent_at = CASE WHEN :ok THEN :now ELSE sent_at END
         WHERE id = :id
    """), {"s": status, "n": next_at, "e": (error or None) and str(error)[:300], "ok": ok, "now": now, "id": row["id"]})
    await db.commit()


def payload(row: dict, company: str, now: datetime) -> dict:
    secret = os.getenv(ENV_SECRET) or ""
    base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("APP_PUBLIC_URL") or "https://clonexa-backend-production.up.railway.app").rstrip("/")
    files = []
    for i, a in enumerate(ws._json(row.get("attachments"), [])):
        if a.get("kind") == "card_png":
            data = {"c": row["company_id"], "k": "card_png", "d": int(row["id"]), "i": i, "exp": int((now + LINK_TTL).timestamp())}
        else:
            data = {"c": row["company_id"], "k": a.get("kind"), "f": a.get("from"), "t": a.get("to"), "exp": int((now + LINK_TTL).timestamp())}
        token = sign(secret, data)
        files.append({"url": f"{base}/api/v1/group-reports/files/{token}", "file_name": a.get("file_name"), "mimetype": a.get("mimetype")})
    is_mail = row["channel"] == "email"
    body = str(row["body"] or "")
    is_html = is_mail and body.startswith(HTML_MARK)
    return {"delivery_id": int(row["id"]), "notice_id": int(row["notice_id"]), "company": company, "kind": row["kind"],
            "kind_label": KINDS.get(row["kind"], row["kind"]), "test_mode": bool(row["test"]), "channel": row["channel"],
            "destination": row["destination"],
            "to": [t for t in str(row["target"]).split(",") if t] if is_mail else row["target"],
            "subject": row.get("subject") or "", "text": body[len(HTML_MARK):] if is_html else body, "html": is_html, "attachments": files,
            "attempt": int(row.get("attempts") or 1), "max_attempts": MAX_ATTEMPTS}


async def post(data: dict) -> tuple[bool, Optional[str]]:
    import httpx

    url, secret = os.getenv(ENV_URL) or "", os.getenv(ENV_SECRET) or ""
    if not url or not secret:
        return False, f"Falta configurar {ENV_URL} / {ENV_SECRET} en Railway"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            res = await client.post(url, json=data, headers={SECRET_HEADER: secret})
    except httpx.HTTPError as exc:
        return False, f"n8n no respondió ({type(exc).__name__})"
    if res.status_code >= 300:
        return False, f"n8n respondió {res.status_code}"
    try:
        body = res.json()
    except ValueError:
        body = {}
    if isinstance(body, dict) and body.get("ok") is False:
        return False, str(body.get("error") or "n8n no pudo entregar")[:300]
    return True, None


async def deliver_company(db: AsyncSession, company_id: Any, *, sender=None, sleep=None, now_fn=None, limit: int = MAX_SENDS_PER_PASS) -> int:
    """Envia los pendientes de UNA empresa, uno por uno, con 3-6 s entre mensajes."""
    sender = sender or post
    sleep = sleep or asyncio.sleep
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    cid = str(company_id)
    company = await company_name(db, cid)
    sent = 0
    for _ in range(limit):
        row = await _take(db, cid, now_fn())
        if not row:
            break
        if sent:
            await sleep(random.uniform(*SEND_GAP))
        row["company_id"] = cid
        try:
            ok, error = await sender(payload(row, company, now_fn()))
        except Exception as exc:  # nunca frena el ciclo
            ok, error = False, type(exc).__name__
        await _finish(db, row, ok, error, now_fn())
        sent += 1
    return sent


async def purge(db: AsyncSession) -> None:
    await db.execute(text("DELETE FROM wa_report_notices WHERE created_at < now() - make_interval(days => :d)"), {"d": PURGE_DAYS})
    await db.execute(text("DELETE FROM wa_timesheet_receipts WHERE received_at < now() - make_interval(days => :d)"), {"d": PURGE_DAYS})
    await db.execute(text("DELETE FROM wa_autoreplies WHERE local_date < CURRENT_DATE - 30"))
    await db.commit()


async def run_all(db: AsyncSession) -> int:
    total = 0
    for cid in await companies_on(db):
        try:
            total += sum((await plan_company(db, cid)).values())
        except Exception as exc:  # una empresa con datos raros no frena a las demas
            await db.rollback()
            log.warning("Avisos WhatsApp: planificacion fallo para %s: %s", cid, type(exc).__name__)
        try:
            await deliver_company(db, cid)
        except Exception as exc:
            await db.rollback()
            log.warning("Avisos WhatsApp: envio fallo para %s: %s", cid, type(exc).__name__)
    return total


async def loop() -> None:
    from app.core.database import AsyncSessionLocal

    last_purge = 0.0
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_all(db)
                if _time.monotonic() - last_purge > 24 * 3600:
                    last_purge = _time.monotonic()
                    await purge(db)
        except Exception as exc:  # nunca tumba el servidor
            log.warning("Avisos WhatsApp no pudieron correr: %s", type(exc).__name__)
        await asyncio.sleep(LOOP_SECONDS)


def start_loop() -> None:
    asyncio.get_event_loop().create_task(loop())


# ------------------------------------------------------------------ historial
async def history(db: AsyncSession, company_id: Any, limit: int = 100) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT d.id, d.kind, d.channel, d.destination, d.status, d.attempts, d.last_error, d.test, d.created_at, d.sent_at,
               n.local_date, d.subject, left(d.body, 600) AS body
        FROM wa_report_deliveries d JOIN wa_report_notices n ON n.id = d.notice_id AND n.company_id = d.company_id
        WHERE d.company_id = CAST(:c AS uuid)
        ORDER BY d.created_at DESC, d.id DESC LIMIT :n
    """), {"c": str(company_id), "n": max(1, min(int(limit), 300))})).mappings().all()
    labels = {**KINDS, **EXTRA_KINDS}
    return [{"id": int(r["id"]), "kind": r["kind"], "kind_label": labels.get(r["kind"], r["kind"]), "channel": r["channel"],
             "destination": r["destination"], "status": r["status"], "attempts": int(r["attempts"] or 0), "error": r["last_error"],
             "test": bool(r["test"]), "created_at": ws.iso(r["created_at"]), "sent_at": ws.iso(r["sent_at"]),
             "date": r["local_date"].isoformat() if r["local_date"] else None, "subject": r["subject"], "text": r["body"]} for r in rows]


# ------------------------------------------------------------------ entradas desde n8n (timesheets)
def _reply(cfg: dict, target: str, body: str) -> dict:
    test = cfg.get("test_mode") is not False
    return {"to": (cfg.get("own_number") or "") if test else target, "text": (TEST_PREFIX + body) if test else body}


async def classify(db: AsyncSession, company_id: Any, body: Any, now: Optional[datetime] = None) -> dict:
    """Que hacer con un mensaje o correo que llego: save (guardar la foto en Drive), autoreply o ignore.
    Nunca se responde en los grupos (salvo el "Recibida" de la foto del grupo semanal)."""
    now = now or datetime.now(timezone.utc)
    cid = str(company_id)
    body = body if isinstance(body, dict) else {}
    cfg = await get_config(db, cid)
    ops = {o["id"]: o for o in await operations(db, cid, cfg)}
    places = {p["id"]: p for p in await locations(db, cid)}
    sup = cfg.get("supervisor") or {}
    channel = str(body.get("channel") or "")
    has_media = body.get("has_media") is True
    location_id: Optional[str] = None
    reply_to = ""
    if channel == "whatsapp":
        jid = str(body.get("jid") or "")
        if body.get("from_me") is True:
            return {"action": "ignore"}
        if jid.endswith("@g.us"):
            weekly = ops.get(cfg.get("weekly_location_id") or "")
            if has_media and weekly and weekly.get("group_jid") and jid == weekly["group_jid"]:
                location_id, reply_to = weekly["id"], jid
            else:
                return {"action": "ignore"}
        else:
            number = digits(jid.split("@")[0])
            known = {digits(cfg.get("own_number"))} | {digits(o.get("phone")) for o in cfg.get("owners") or []}
            if number and number == digits(sup.get("phone")):
                if not has_media:
                    return {"action": "ignore"}
                location_id, reply_to = (sup.get("location_id") or None), number
            elif not number or number in known:
                return {"action": "ignore"}
            else:
                tz = ws.zone(next(iter(ops.values()))["tz"] if ops else "America/New_York")
                fresh = (await db.execute(text("""
                    INSERT INTO wa_autoreplies (company_id, sender, local_date) VALUES (CAST(:c AS uuid), :s, :d)
                    ON CONFLICT DO NOTHING RETURNING sender
                """), {"c": cid, "s": number[:80], "d": now.astimezone(tz).date()})).first()
                await db.commit()
                return {"action": "autoreply", "reply": _reply(cfg, number, AUTOREPLY_TEXT)} if fresh else {"action": "ignore"}
    elif channel == "email":
        sender = str(body.get("from_email") or "").strip().lower()
        m = re.search(r"[\w.+-]+@[\w.-]+", sender)
        sender = m.group(0) if m else sender
        subject = str(body.get("subject") or "").lower()
        if not has_media or not sender or sender == str(cfg.get("clonexa_email") or "").lower():
            return {"action": "ignore"}
        if sender == str(sup.get("email") or "").lower() and sup.get("email"):
            location_id = sup.get("location_id") or None
        else:
            row = (await db.execute(text("""
                SELECT work_location_id::text FROM employees WHERE company_id = CAST(:c AS uuid) AND lower(COALESCE(email, '')) = :e
                  AND lower(COALESCE(status, 'active')) IN ('active', 'activo') LIMIT 1
            """), {"c": cid, "e": sender})).first()
            if row and row[0] in ops:
                location_id = row[0]
            elif "timesheet" in subject:
                location_id = next((oid for oid, o in ops.items() if o["name"].lower() in subject), None)
            else:
                return {"action": "ignore"}
    else:
        return {"action": "ignore"}
    place = places.get(location_id or "")
    tz = (place or {}).get("timezone") or "America/New_York"
    folder_name = (place or {}).get("name") or "Sin operación"
    out = {"action": "save", "location_id": location_id, "operation": folder_name,
           "date": now.astimezone(ws.zone(tz)).date().isoformat(),
           "drive_parent_id": (cfg.get("drive_folders") or {}).get(location_id or "_other") or (cfg.get("drive_folders") or {}).get("_other") or "",
           "folder_path": ["VOLTAGE", "Timesheets", folder_name]}
    if reply_to:
        out["reply"] = _reply(cfg, reply_to, RECEIVED_TEXT)
    return out


async def received(db: AsyncSession, company_id: Any, body: Any, now: Optional[datetime] = None) -> dict:
    """n8n guardo la foto en Drive: se anota (asi no sale el recordatorio de las 9:00) y queda en el historial."""
    cid = str(company_id)
    body = body if isinstance(body, dict) else {}
    locs = {p["id"]: p for p in await locations(db, cid)}
    lid = str(body.get("location_id") or "")
    lid = lid if lid in locs else None
    source = "email" if body.get("source") == "email" else "whatsapp"
    sender = _text(body.get("sender"), 200)
    url = str(body.get("drive_url") or "")[:600]
    url = url if url.startswith("https://") else None
    await db.execute(text("""
        INSERT INTO wa_timesheet_receipts (company_id, location_id, source, sender, file_name, drive_url, received_at)
        VALUES (CAST(:c AS uuid), CAST(:l AS uuid), :s, :who, :f, :u, :at)
    """), {"c": cid, "l": lid, "s": source, "who": sender or None, "f": _text(body.get("file_name"), 300) or None, "u": url,
           "at": now or datetime.now(timezone.utc)})
    await db.commit()
    op = (locs.get(lid) or {}).get("name") or "Sin operación"
    await claim(db, cid, f"received:{uuid.uuid4().hex}", "received", location_id=lid, day=(now or datetime.now(timezone.utc)).date(), slot=0,
                deliveries=[{"channel": "drive", "destination": f"Drive {op} ({'correo' if source == 'email' else 'WhatsApp'} {sender})"[:200],
                             "target": url or "drive", "body": _text(body.get("file_name"), 300), "test": False, "status": "received"}])
    return {"ok": True, "location_id": lid}
