"""Oficina 3D (Consola v2+, interno de Clonexa): reglas puras y estado de n8n.

Lo ve SOLO Admin V2 / v2+ (las rutas viven en app/web/oficina_routes.py con GUARD). Ninguna
empresa cliente ve nada nuevo. Aqui no hay SQL: los datos de la base salen de
app/services/oficina_data.py (cada consulta por empresa filtra por company_id).

- Agentes del piso CLONEXA: cada uno sale de flujos REALES de n8n (nombres exactos) y/o de la
  base. El flujo "Oficina - Estado" de n8n responde todo en una sola llamada; aqui se consulta con
  cache de 30 s (nunca mas de 2 veces por minuto) y "stale-while-revalidate": la pagina recibe la
  ultima respuesta al instante y la siguiente se pide por detras.
- Estados: trabajando (corriendo o corrio bien en los ultimos 15 min), esperando/cafe (activo sin
  trabajo reciente), error (la ultima ejecucion fallo), en entrenamiento (flujo inactivo o pendiente
  de configurar) y sin datos (el flujo no existe o n8n no responde: nunca se inventa).
- Plantillas de piso: taller, restaurante, bar, campo y general. Privacidad: primer nombre +
  inicial del apellido y cargo (o solo cargo). Nada de dinero, GPS ni datos personales extra.
- Editor (fase 1.5): sin imagenes ni modelos cargados (una imagen plana pierde la animacion). Lo ya
  cargado queda en el bucket y en la base, pero no se usa; las subidas responden 410.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
import unicodedata
from html import escape as html_escape
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger("clonexa.oficina")

BOGOTA = ZoneInfo("America/Bogota")
WORK_WINDOW = timedelta(minutes=15)
N8N_TTL = 30.0          # segundos: cache del flujo "Oficina - Estado"
N8N_TIMEOUT = 8.0
N8N_HEADER = "X-Oficina-Secret"
ENV_URL = "OFICINA_N8N_URL"
ENV_SECRET = "OFICINA_N8N_SECRET"

STATES = ("work", "wait", "err", "train", "nodata")
STYLES = ("lego", "anime", "real")  # estilo de los pisos clasicos; "imagen" y "modelo" ya no se usan
ACCESSORIES = ("none", "audifonos", "gafas", "gorra", "casco", "chaleco", "delantal", "corbata")
BODIES = ("medio", "delgado", "robusto", "alto")
HAIRSTYLES = ("corto", "largo", "rizado", "recogido", "rapado", "calvo")
TEMPLATES = ("taller", "restaurante", "bar", "campo", "general")
TEMPLATE_LABEL = {"taller": "Taller de costura", "restaurante": "Restaurante", "bar": "Bar", "campo": "Operación en campo",
                  "general": "Oficina general"}
PRIVACY = ("nombre", "cargo")
# Editor (pisos aprobados): genero y personaje de Mixamo de cada genero; tunica, barba (solo hombres) y su color.
GENDERS = ("hombre", "mujer")
MIXAMO_BY_GENDER = {"hombre": ("Remy", "Ch01_nonPBR", "Ch06_nonPBR", "Ch42_nonPBR", "Ch17_nonPBR"),
                    "mujer": ("Ch07_nonPBR", "Ch21_nonPBR", "Ch22_nonPBR")}
YES_NO = ("si", "no")
UNIFORMS = ("costura", "cocina", "mesero", "caja", "domiciliario", "barman", "dj", "tecnico")
UNIFORM_LABEL = {"costura": "Operaria de costura", "cocina": "Cocinero/a", "mesero": "Mesero/a", "caja": "Cajero/a",
                 "domiciliario": "Domiciliario", "barman": "Barman", "dj": "DJ", "tecnico": "Técnico de campo"}
# Cuantos muñecos se ven por piso (el resto queda en un letrero "+N en turno").
VISIBLE = {"taller": 10, "restaurante": 12, "bar": 10, "campo": 5, "general": 10}

# Empresas vivas conocidas -> plantilla (si el dueño no eligio otra en la oficina).
KNOWN_TEMPLATES = {
    "d63cf68c-be5b-4a30-aee4-341973018db1": "taller",       # Velvet
    "7625872c-f941-4479-a27b-f8443be953c5": "restaurante",  # ASADERO EL SOCIO
    "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4": "bar",          # The Time Machine
    "f1e8f774-f052-49ca-880a-268805f07db0": "campo",        # VOLTAGE
}
BAR_DEFAULT_DAY = {"open": "18:00", "close": "04:00"}

# ------------------------------------------------------------------ agentes del piso CLONEXA
# flows: nombres EXACTOS de n8n (se comparan sin tildes ni mayusculas). pending: el flujo existe
# pero falta configurarlo (queda "en entrenamiento" aunque este activo).
AGENTS: list[dict[str, Any]] = [
    {"id": "director", "human": True, "flows": [], "source": "Tú. Las aprobaciones llegan por Telegram (@CloNEXA_bot)."},
    {"id": "asistente", "flows": ["Nexa - Bot de comandos"]},
    {"id": "creativo", "flows": [], "sheet": "calendar", "source": "Hoja \"Nexa - Calendario de contenido\" (piezas por semana)."},
    {"id": "contenido", "flows": ["Nexa - Vista previa", "Nexa - Publicar del día"]},
    {"id": "planb", "flows": ["Nexa - Plan B"]},
    {"id": "tiktok", "flows": ["Nexa - TikTok"], "pending": "Faltan las claves de producción de TikTok (hoy solo hay claves de prueba)."},
    {"id": "analista", "flows": [], "sheet": "report", "source": "Pestaña \"Reporte semanal\" de la hoja de contenido."},
    {"id": "ventas", "flows": ["Nexa - WhatsApp ventas"], "db": "wa"},
    {"id": "correos", "flows": ["Nexa - Correos", "Nexa - Correos prospección"], "db": "mail"},
    {"id": "prospecta", "flows": ["Nexa - Prospección"], "db": "prospects"},
    {"id": "comunidad", "flows": ["Nexa - Leads DEMO"]},
    {"id": "mensajero", "flows": ["VOLTAGE envíos"], "db": "voltage_sends"},
    {"id": "archivista", "flows": ["VOLTAGE timesheets"], "db": "timesheets"},
    {"id": "lector", "flows": ["Clonexa - Leer carta"], "db": "menu"},
    {"id": "guardian", "flows": ["Nexa - Errores"]},
]
# Piso aprobado de Clonexa: area de cada agente (un flujo nuevo de n8n cae en la suya por su nombre).
AGENT_AREA = {"director": "direccion", "asistente": "juntas", "creativo": "marketing", "contenido": "marketing", "planb": "marketing",
              "tiktok": "marketing", "analista": "marketing", "ventas": "ventas", "correos": "ventas", "prospecta": "ventas",
              "comunidad": "ventas", "mensajero": "bots", "archivista": "bots", "lector": "bots", "guardian": "bots"}
AGENT_IDS = tuple(a["id"] for a in AGENTS)


def fold(value: Any) -> str:
    """Sin tildes, minusculas y espacios simples (para comparar nombres de flujos)."""
    plain = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", plain).strip().casefold()


def parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        out = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return out if out.tzinfo else out.replace(tzinfo=timezone.utc)


def iso(value: Any) -> Optional[str]:
    moment = parse_dt(value)
    return moment.isoformat() if moment else None


def hhmm(value: Any, tz: ZoneInfo = BOGOTA) -> str:
    moment = parse_dt(value)
    return moment.astimezone(tz).strftime("%H:%M") if moment else ""


def when_label(value: Any, now: datetime, tz: ZoneInfo = BOGOTA) -> str:
    """'hoy 14:05', 'ayer 22:10' o '08/11 07:00' (hora de Bogota)."""
    moment = parse_dt(value)
    if not moment:
        return ""
    local, today = moment.astimezone(tz), now.astimezone(tz).date()
    if local.date() == today:
        return f"hoy {local:%H:%M}"
    if local.date() == today - timedelta(days=1):
        return f"ayer {local:%H:%M}"
    return f"{local:%d/%m %H:%M}"


def ago_label(value: Any, now: datetime) -> str:
    moment = parse_dt(value)
    if not moment:
        return "sin actividad registrada"
    minutes = int(max(0.0, (now - moment).total_seconds()) // 60)
    if minutes < 1:
        return "hace menos de 1 min"
    if minutes < 60:
        return f"hace {minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"hace {hours} h"
    return f"hace {hours // 24} días"


# ------------------------------------------------------------------ estados de agentes
def index_flows(workflows: Any) -> dict[str, dict]:
    """Los flujos que devolvio n8n, por nombre doblado (sin tildes)."""
    out: dict[str, dict] = {}
    for w in workflows if isinstance(workflows, list) else []:
        if isinstance(w, dict) and w.get("name"):
            out[fold(w["name"])] = w
    return out


def flow_state(flow: dict, now: datetime) -> str:
    """Estado de UN flujo de n8n con las reglas de la oficina."""
    if not flow.get("active"):
        return "train"
    if flow.get("running"):
        return "work"
    last = flow.get("last") if isinstance(flow.get("last"), dict) else None
    if last and str(last.get("status") or "").lower() in ("error", "crashed", "failed"):
        return "err"
    ok_at = parse_dt(flow.get("last_ok_at")) or (parse_dt(last.get("stopped_at") or last.get("started_at"))
                                                  if last and str(last.get("status") or "").lower() == "success" else None)
    if ok_at and now - ok_at <= WORK_WINDOW:
        return "work"
    return "wait"


def agent_state(flows: list[Optional[dict]], now: datetime, *, n8n_ok: bool, pending: Optional[str] = None) -> str:
    """Estado de un agente con uno o varios flujos. Sin n8n o sin flujo -> sin datos (gris)."""
    if not n8n_ok:
        return "nodata"
    found = [f for f in flows if f]
    if not found:
        return "nodata"
    if pending:
        return "train"
    states = [flow_state(f, now) for f in found]
    if all(s == "train" for s in states):
        return "train"
    if any(f.get("running") and f.get("active") for f in found):
        return "work"
    if "err" in states:
        return "err"
    if "work" in states:
        return "work"
    return "wait"


def flow_lines(flows: list[Optional[dict]], now: datetime) -> list[str]:
    """Lo que hicieron hoy los flujos (ejecuciones reales de n8n)."""
    lines: list[str] = []
    for f in flows:
        if not f:
            continue
        runs, errors = int(f.get("today_runs") or 0), int(f.get("today_errors") or 0)
        name = str(f.get("name") or "")
        if f.get("running"):
            lines.append(f"{name}: corriendo ahora")
        last = f.get("last") if isinstance(f.get("last"), dict) else None
        if runs:
            more = "+" if f.get("today_runs_capped") else ""
            lines.append(f"{name}: {runs}{more} {'ejecución' if runs == 1 else 'ejecuciones'} hoy" + (f" ({errors} con error)" if errors else ""))
        elif last:
            status = "bien" if str(last.get("status")) == "success" else "con error" if str(last.get("status")) in ("error", "crashed") else str(last.get("status") or "")
            lines.append(f"{name}: última {when_label(last.get('stopped_at') or last.get('started_at'), now)} · {status}")
        else:
            lines.append(f"{name}: sin ejecuciones guardadas")
        if not f.get("active"):
            lines.append(f"{name}: inactivo en n8n")
    return lines


def source_label(agent: dict, flows: list[Optional[dict]]) -> str:
    if agent.get("source"):
        return agent["source"]
    names = [f"\"{f['name']}\"" if f else f"\"{n}\" (no existe en n8n)" for n, f in zip(agent["flows"], flows)]
    return "Flujo " + " y ".join(names) if len(names) == 1 else "Flujos " + " y ".join(names)


def build_agents(n8n: dict, db_lines: dict[str, list[str]], now: datetime) -> list[dict]:
    """Los 15 personajes del piso CLONEXA con su estado real, lo que hicieron hoy y su fuente."""
    ok = bool(n8n.get("ok"))
    flows_by = index_flows(n8n.get("workflows"))
    cal, report = n8n.get("calendar") or {}, n8n.get("report") or {}
    out = []
    for a in AGENTS:
        flows = [flows_by.get(fold(name)) for name in a["flows"]]
        extra = list(db_lines.get(a["id"]) or [])
        last_run = None
        if a.get("human"):
            state, today = "work", extra
        elif a.get("sheet") == "calendar":
            if ok and cal.get("ok"):
                week = int(cal.get("week_pieces") or 0)
                state = "work" if week else "wait"
                today = [f"{week} {'pieza' if week == 1 else 'piezas'} en el calendario esta semana",f"{int(cal.get('ready') or 0)} en \"Listo para aprobar\""]
                nxt = cal.get("next") or {}
                if nxt.get("fecha"):
                    today.append(f"Próxima: {nxt.get('fecha')} · {nxt.get('formato') or ''} {nxt.get('tema') or ''}".strip())
            else:
                state, today = "nodata", []
        elif a.get("sheet") == "report":
            last_day = None
            try:
                last_day = date.fromisoformat(str(report.get("last_date") or "")[:10]) if report.get("last_date") else None
            except ValueError:
                last_day = None
            if ok and report.get("ok"):
                today_d = now.astimezone(BOGOTA).date()
                if last_day is None:
                    state, today = "train", ["Aún no hay reportes en la pestaña"]
                else:
                    state = "work" if last_day == today_d else "wait"
                    today = [f"Último reporte: {last_day:%d/%m/%Y}", f"{int(report.get('rows') or 0)} filas en la pestaña"]
            else:
                state, today = "nodata", []
        else:
            state = agent_state(flows, now, n8n_ok=ok, pending=a.get("pending"))
            today = (flow_lines(flows, now) if ok else []) + extra
            if a.get("pending") and any(flows):
                today.insert(0, a["pending"])
            finished = [f.get("last") for f in flows if f and isinstance(f.get("last"), dict)]
            finished.sort(key=lambda x: str(x.get("started_at") or ""), reverse=True)
            if finished:
                last_run = {"at": iso(finished[0].get("stopped_at") or finished[0].get("started_at")), "status": finished[0].get("status")}
        if state == "nodata" and not today:
            today = ["Sin datos: " + ("n8n no respondió" if not ok else "el flujo no existe o no tiene datos")]
        elif state == "nodata" and not ok:
            today = ["Sin datos de n8n (no respondió)"] + today
        elif state == "nodata":
            today = ["Sin datos: el flujo no existe en n8n"] + today
        out.append({"id": a["id"], "state": state, "today": today[:6], "source": source_label(a, flows) if not a.get("human") else a["source"],
                    "flows": [{"name": n, "exists": bool(f), "active": bool(f and f.get("active"))} for n, f in zip(a["flows"], flows)],
                    "last_run": last_run, "human": bool(a.get("human"))})
    return out


def n8n_feed(n8n: dict, now: datetime, limit: int = 12) -> list[dict]:
    """Ejecuciones reales terminadas (y errores) de los flujos de los agentes."""
    if not n8n.get("ok"):
        return []
    known = {fold(n) for a in AGENTS for n in a["flows"]}
    out = []
    for e in n8n.get("recent") or []:
        if not isinstance(e, dict) or fold(e.get("workflow")) not in known:
            continue
        at = parse_dt(e.get("stopped_at") or e.get("started_at"))
        if not at or now - at > timedelta(hours=24):
            continue
        status = str(e.get("status") or "")
        bad = status in ("error", "crashed", "failed")
        name = html_escape(str(e.get("workflow") or ""))
        text = f"⚠️ <b>{name}</b> falló" if bad else f"<b>{name}</b> terminó bien"
        out.append({"at": at.isoformat(), "kind": "error" if bad else "run", "text": text})
    out.sort(key=lambda x: x["at"], reverse=True)
    return out[:limit]


# ------------------------------------------------------------------ pisos y personal
def deduce_template(company_id: str, modules: set[str], *, has_locations: bool, overnight: bool) -> Optional[str]:
    """Plantilla por lo que Clonexa ya sabe de la empresa. None = no se puede deducir."""
    known = KNOWN_TEMPLATES.get(str(company_id))
    if known:
        return known
    mods = {fold(m) for m in modules}
    if has_locations:
        return "campo"
    if mods & {"production", "references"}:
        return "taller"
    if mods & {"hospitality", "waiter_ordering", "carta"}:
        return "bar" if overnight or "loyalty" in mods else "restaurante"
    return None


def short_name(full_name: Any) -> str:
    """Primer nombre + inicial del (primer) apellido: 'Ana María Pérez Gómez' -> 'Ana P.'."""
    parts = [p for p in re.split(r"\s+", str(full_name or "").strip()) if p]
    if not parts:
        return ""
    first = parts[0].capitalize() if parts[0].isupper() or parts[0].islower() else parts[0]
    if len(parts) == 1:
        return first
    surname = parts[2] if len(parts) >= 4 else parts[1]
    return f"{first} {surname[0].upper()}."


def role_label(role: Any) -> str:
    raw = re.sub(r"[_\s]+", " ", str(role or "")).strip()
    return raw[:1].upper() + raw[1:] if raw else "Personal"


def uniform_for(role: Any, template: str) -> str:
    """Plantilla de uniforme por el cargo; si el cargo no dice nada, la del tipo de piso."""
    r = fold(role)
    rules = (("domicil", "domiciliario"), ("repart", "domiciliario"), ("barman", "barman"), ("bartend", "barman"), ("barra", "barman"),
             ("dj", "dj"), ("music", "dj"), ("cocin", "cocina"), ("chef", "cocina"), ("parrill", "cocina"), ("caja", "caja"),
             ("cajer", "caja"), ("meser", "mesero"), ("salon", "mesero"), ("costur", "costura"), ("operari", "costura"),
             ("confecc", "costura"), ("tecnic", "tecnico"), ("instal", "tecnico"), ("campo", "tecnico"))
    for needle, uniform in rules:
        if re.search(rf"\b{needle}", r):
            if uniform == "costura" and template == "campo":
                return "tecnico"
            return uniform
    return {"taller": "costura", "restaurante": "mesero", "bar": "barman", "campo": "tecnico"}.get(template, "")


def staff_out(rows: list[dict], template: str, privacy: str) -> dict:
    """Personal con turno ABIERTO del piso: etiqueta segun privacidad, uniforme y pausa.
    Campo: maximo 5 por operacion + '+N'; el resto de pisos: VISIBLE[plantilla] + '+N'."""
    def person(r: dict) -> dict:
        role = role_label(r.get("employee_role"))
        name = short_name(r.get("employee_name"))
        label = role if privacy == "cargo" or not name else f"{name} · {role}"
        return {"key": hashlib.sha256(f"{r.get('employee_id')}".encode()).hexdigest()[:12], "label": label, "role": role,
                "uniform": uniform_for(r.get("employee_role"), template), "paused": str(r.get("status")) == "on_break",
                "op": str(r.get("work_location_name") or "").strip() or "Sin lugar asignado"}

    people = [person(r) for r in rows]
    total = len(people)
    if template == "campo":
        groups: dict[str, list[dict]] = {}
        for p in people:
            groups.setdefault(p["op"], []).append(p)
        ops = [{"name": name, "total": len(items), "visible": items[:VISIBLE["campo"]], "extra": max(0, len(items) - VISIBLE["campo"])}
               for name, items in sorted(groups.items(), key=lambda kv: fold(kv[0]))]
        return {"total": total, "visible": [p for o in ops for p in o["visible"]], "extra": sum(o["extra"] for o in ops), "ops": ops}
    cap = VISIBLE.get(template, 10)
    return {"total": total, "visible": people[:cap], "extra": max(0, total - cap), "ops": []}


# ------------------------------------------------------------------ dia del bar
def clock(value: Any) -> Optional[tuple[int, int]]:
    try:
        h, m = str(value or "").split(":")[:2]
        h, m = int(h), int(m)
    except (TypeError, ValueError):
        return None
    return (h, m) if 0 <= h < 24 and 0 <= m < 60 else None


def jornada(now: datetime, tz: ZoneInfo, cfg: Optional[dict]) -> tuple[datetime, datetime, str]:
    """Ventana [inicio, fin) del dia de trabajo. Bar (cierre antes de la apertura, p. ej. 18:00-04:00):
    la jornada en curso o la de esta noche si aun no abre. Sin jornada: medianoche a medianoche."""
    local = now.astimezone(tz)
    o, c = clock((cfg or {}).get("open")), clock((cfg or {}).get("close"))
    if o and c and c < o:
        close_today = local.replace(hour=c[0], minute=c[1], second=0, microsecond=0)
        day = local.date() - timedelta(days=1) if local < close_today else local.date()
        start = datetime(day.year, day.month, day.day, o[0], o[1], tzinfo=tz)
        end = datetime(day.year, day.month, day.day, c[0], c[1], tzinfo=tz) + timedelta(days=1)
        return start, end, f"Jornada {o[0]:02d}:{o[1]:02d}–{c[0]:02d}:{c[1]:02d}"
    start = datetime(local.year, local.month, local.day, tzinfo=tz)
    return start, start + timedelta(days=1), "Hoy"


# ------------------------------------------------------------------ editor: validacion
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
KEY_RE = re.compile(r"^(agente:[a-z]{3,20}|rep|plantilla:[a-z]{2,20}|persona:[0-9a-f]{12})$")


class Rejected(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message = message
        self.status = status


def sniff_image(raw: bytes) -> Optional[tuple[str, str]]:
    """(content-type, extension) por la firma real; None si no es PNG/JPG/WebP (logo del panel inicial)."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def clean_character(body: Any) -> dict:
    """Campos editables de un personaje (lo demas se ignora)."""
    if not isinstance(body, dict):
        raise Rejected("Datos no válidos.")
    out: dict[str, Any] = {}
    for field, size in (("nombre", 80), ("rol", 40), ("tarea", 120)):
        if field in body:
            out[field] = re.sub(r"[\x00-\x1f<>]", "", str(body.get(field) or "")).strip()[:size]
    if "estilo" in body:
        if body["estilo"] not in STYLES:
            raise Rejected("Estilo no válido.")
        out["estilo"] = body["estilo"]
    for field, options in (("cuerpo", BODIES), ("peinado", HAIRSTYLES)):
        if field in body:
            value = str(body.get(field) or "")
            if value and value not in options:
                raise Rejected("Opción no válida en " + field + ".")
            out[field] = value
    if "accesorio" in body:
        value = str(body.get("accesorio") or "none")
        if value not in ACCESSORIES:
            raise Rejected("Accesorio no válido.")
        out["accesorio"] = value
    if "genero" in body:
        value = str(body.get("genero") or "")
        if value and value not in GENDERS:
            raise Rejected("Género no válido.")
        out["genero"] = value
    if "personaje" in body:
        value = str(body.get("personaje") or "")
        if value and not any(value in names for names in MIXAMO_BY_GENDER.values()):
            raise Rejected("Personaje no válido.")
        gender = out.get("genero") or str(body.get("genero") or "")
        if value and gender in MIXAMO_BY_GENDER and value not in MIXAMO_BY_GENDER[gender]:
            raise Rejected("Ese personaje no es del género elegido.")
        out["personaje"] = value
    for field in ("tunica", "barba"):
        if field in body:
            value = str(body.get(field) or "")
            if value and value not in YES_NO:
                raise Rejected(f"Opción no válida en {field}.")
            out[field] = value
    if out.get("barba") == "si" and (out.get("genero") or body.get("genero")) == "mujer":
        raise Rejected("La barba es solo para personajes hombres.")
    for field in ("color_ropa", "color_pantalon", "color_pelo", "color_piel", "color_accesorio", "color_barba"):
        if field in body:
            value = str(body.get(field) or "")
            if value and not HEX.match(value):
                raise Rejected(f"Color no válido en {field}.")
            out[field] = value.lower()
    return out


def check_key(clave: str) -> str:
    clave = str(clave or "").strip()
    if clave.startswith("agente:") and clave.split(":", 1)[1] not in AGENT_IDS:
        raise Rejected("Personaje no válido.", 404)
    if clave.startswith("plantilla:") and clave.split(":", 1)[1] not in UNIFORMS:
        raise Rejected("Plantilla no válida.", 404)
    if not KEY_RE.match(clave):
        raise Rejected("Personaje no válido.", 404)
    return clave


# ------------------------------------------------------------------ n8n "Oficina - Estado"
Fetcher = Callable[[str, str], Awaitable[dict]]


async def _http_fetch(url: str, secret: str) -> dict:
    import httpx

    async with httpx.AsyncClient(timeout=N8N_TIMEOUT) as client:
        r = await client.get(url, headers={N8N_HEADER: secret, "Accept": "application/json"})
    if r.status_code != 200:
        raise RuntimeError(f"n8n respondió {r.status_code}")
    data = r.json()
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        raise RuntimeError("n8n respondió algo que no es un objeto")
    return data


class N8nCache:
    """Cache de 30 s con una sola consulta a la vez y 'stale-while-revalidate'."""

    def __init__(self, fetch: Fetcher = _http_fetch, ttl: float = N8N_TTL, clock: Callable[[], float] = time.monotonic):
        self.fetch, self.ttl, self.clock = fetch, ttl, clock
        self.data: Optional[dict] = None
        self.at: Optional[float] = None
        self.calls: list[float] = []
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    def reset(self) -> None:
        self.data, self.at, self.calls, self._task = None, None, [], None

    def fresh(self) -> bool:
        return self.at is not None and self.clock() - self.at < self.ttl

    async def _refresh(self) -> dict:
        async with self._lock:
            if self.fresh() and self.data is not None:
                return self.data
            url, secret = os.getenv(ENV_URL, "").strip(), os.getenv(ENV_SECRET, "").strip()
            now = self.clock()
            self.calls = [c for c in self.calls if now - c < 60.0] + [now]
            if not url or not secret:
                data = {"ok": False, "error": "La oficina aún no tiene configurado el flujo de n8n."}
            else:
                try:
                    data = await self.fetch(url, secret)
                    data = {**data, "ok": data.get("ok", True) is not False}
                except Exception as error:  # n8n caido, lento o con respuesta rara: sin datos, nunca inventar
                    log.warning("oficina: n8n no respondió (%s)", type(error).__name__)
                    data = {"ok": False, "error": "n8n no respondió."}
            data["fetched_at"] = datetime.now(timezone.utc).isoformat()
            self.data, self.at = data, self.clock()
            return data

    async def get(self, *, wait_first: float = 4.0) -> dict:
        if self.data is not None and self.fresh():
            return self.data
        if self.data is not None:
            if not self._task or self._task.done():
                self._task = asyncio.create_task(self._refresh())
            return self.data
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._refresh())
        try:
            return await asyncio.wait_for(asyncio.shield(self._task), timeout=wait_first)
        except asyncio.TimeoutError:
            return {"ok": False, "error": "n8n tarda en responder.", "pending": True}


N8N = N8nCache()
