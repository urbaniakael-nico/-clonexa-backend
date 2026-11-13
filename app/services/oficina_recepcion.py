"""Oficina 3D · RECEPCION con Nexa (interno de Clonexa, solo Admin V2). Copia viva de los interesados REALES de hoy.

Fuentes (lo que ya existe; nada de ejemplo):
- Conversaciones Nexa (WhatsApp ventas): wa_contacts + ultimo mensaje de wa_messages (ultimas 24 h).
- Prospeccion: prospectos que respondieron el correo o abrieron la landing (prospects.replied_at / opened_at,
  ultimas 24 h; nunca los de prueba ni los de baja).
- n8n "Nexa - Leads DEMO" (comentarios con DEMO/precio/info) y "Nexa - Correos" (correos de clientes potenciales):
  los trae el flujo "Oficina - Estado" (clave reception) ya sin usuario, correo ni texto: solo canal, hora, estado
  y temas por palabras clave.
- Demos agendadas: wa_contacts.demo_at / prospects.demo_at (lo guarda la agenda de Nexa). Si no hay dato, se omite.

PRIVACIDAD: nunca telefono, correo, nombre de la persona ni el texto de sus mensajes. Solo tipo de negocio, zona,
tema corto (por palabras clave) y canal. El nombre del negocio solo sale si es un prospecto (dato publico de Google).
Estados: talking (Nexa respondiendo / activa en 10 min), new (recien llegado), waiting (espera respuesta, N min),
demo (agendada, fecha y hora), idle (sin respuesta / solo abrio la landing). Maximo 8 visibles + "+N".
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from app.services import oficina_data as od
from app.services import oficina_vivo as ov

BOGOTA = ZoneInfo("America/Bogota")
WINDOW = timedelta(hours=24)
ACTIVE = timedelta(minutes=10)
JUST_ARRIVED = timedelta(minutes=2)
VISIBLE = 8
STATES = ("talking", "new", "waiting", "demo", "idle")
ORDER = {s: i for i, s in enumerate(STATES)}
COLOR = {"talking": "#22c55e", "new": "#f20b6d", "waiting": "#f59e0b", "demo": "#a855f7", "idle": "#94a3b8"}
STATE_LABEL = {"talking": "Nexa respondiendo", "new": "Recién llegado", "waiting": "En espera", "demo": "Demo agendada", "idle": "Sin respuesta aún"}
DAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")

# Temas por palabras clave (nunca el texto de la persona). Orden = prioridad.
TOPICS = (
    ("carta_video", r"carta\s*(en\s*)?video|men[uú]\s*(en\s*)?video|video\s*(de\s*la\s*)?carta|carta\s*digital|men[uú]\s*digital", "Carta video"),
    ("qr", r"\bqr\b|mesas?\b", "Mesas QR"),
    ("nomina", r"n[oó]mina|turnos?\b|asistencia|horas?\s+extra|empleados", "Nómina y turnos"),
    ("inventario", r"inventario|bodega|stock", "Inventario"),
    ("domicilios", r"domicilio|delivery|pedidos?\b", "Domicilios"),
    ("bot", r"\bbot\b|whats?app|chatbot|automatiza", "Bot de WhatsApp"),
    ("precio", r"precio|cu[aá]nto|cotiza|costo|valor|tarifa|plan(es)?\b", "Precio"),
    ("demo", r"\bdemo\b|prueba\s+gratis|probar", "Demo"),
    ("info", r"\binfo\b|informaci[oó]n|me\s+interesa|interesad", "Información"),
)
TOPIC_LABEL = {k: label for k, _, label in TOPICS}
BUSINESS = (
    (r"restaurante|asadero|comida|cocina|pizzer|hamburgues|parrilla|cafeter|caf[eé]\b", "Restaurante"),
    (r"\bbar\b|discoteca|licorera|gastrobar|pub\b", "Bar"),
    (r"panader|pasteler|reposter", "Panadería"),
    (r"taller|confecci|costura|textil|ropa|moda", "Taller"),
    (r"tienda|minimercado|supermercado|droguer|almac[eé]n", "Tienda"),
    (r"hotel|hostal", "Hotel"),
    (r"constru|obra|el[eé]ctric|t[eé]cnic|mantenimiento|telecomunic|instalaci|instalador", "Servicios técnicos"),
    (r"vigilancia|seguridad privada|aseo|limpieza|personal en campo|campo", "Empresa de campo"),
    (r"transporte|log[ií]stic|mensajer|despacho|acarreo|mudanza", "Transporte"),
)
PROSPECT_TYPE = {"restaurante": "Restaurante", "bar": "Bar", "cafe": "Café", "panaderia": "Panadería", "taller": "Taller",
                 "fabrica": "Fábrica", "comidas_rapidas": "Comidas rápidas", "electrico": "Eléctricos", "telecom": "Telecomunicaciones",
                 "construccion": "Construcción", "instalador": "Instaladores", "aseo": "Aseo", "vigilancia": "Vigilancia",
                 "transporte": "Transporte",
                 "tienda": "Tienda", "hotel": "Hotel", "discoteca": "Bar"}
EMAIL_RE = re.compile(r"\S+@\S+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{5,}\d")
HANDLE_RE = re.compile(r"@\w+")


def scrub(value: Any, limit: int = 28) -> str:
    """Texto corto y seguro para una etiqueta: sin correos, telefonos, @usuarios ni simbolos raros."""
    s = str(value or "")
    s = EMAIL_RE.sub("", s)
    s = PHONE_RE.sub("", s)
    s = HANDLE_RE.sub("", s)
    s = re.sub(r"[<>{}\[\]\"\\|#*_`~^]", "", s)
    s = re.sub(r"\d{4,}", "", s)
    s = re.sub(r"\s+", " ", s).strip(" ·,.;:-")
    return s[:limit].rstrip()


def topic_keys(*texts: Any) -> list[str]:
    blob = " ".join(str(t or "") for t in texts).lower()
    return [k for k, rx, _ in TOPICS if re.search(rx, blob)]


def topic_label(keys: Iterable[str], fallback: str = "Consulta") -> str:
    ks = [k for k in keys if k in TOPIC_LABEL]
    if not ks:
        return fallback
    labels = [TOPIC_LABEL[k] for k in ks[:2]]
    return labels[0] if len(labels) == 1 else f"{labels[0]} y {labels[1][:1].lower()}{labels[1][1:]}"


def business_label(raw: Any) -> str:
    s = str(raw or "").lower()
    for rx, label in BUSINESS:
        if re.search(rx, s):
            return label
    clean = scrub(raw, 22)
    return clean[:1].upper() + clean[1:] if clean else "Interesado"


def demo_label(at: Optional[datetime]) -> Optional[str]:
    if not at:
        return None
    local = at.astimezone(BOGOTA)
    return f"{DAYS[local.weekday()]} {local:%H:%M}"


def _aware(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _minutes(since: Optional[datetime], now: datetime) -> Optional[int]:
    return max(0, int((now - since).total_seconds() // 60)) if since else None


def vid(source: str, ident: Any) -> str:
    return hashlib.sha256(f"recepcion:{source}:{ident}".encode()).hexdigest()[:12]


# ------------------------------------------------------------------ estados (reglas puras)
def wa_state(now: datetime, *, first_at: Any, last_at: Any, last_dir: Optional[str], last_in: Any, last_out: Any,
             demo_at: Any, stage: str, paused: bool) -> tuple[str, Optional[int]]:
    """Estado de una conversacion de WhatsApp (estado, minutos de espera)."""
    first_at, last_at, last_in, last_out, demo_at = map(_aware, (first_at, last_at, last_in, last_out, demo_at))
    unanswered = last_dir == "in" and (not last_out or (last_in and last_out < last_in))
    if unanswered and last_in:
        if first_at and now - first_at <= JUST_ARRIVED:
            return "new", None
        if (now - last_in) < timedelta(minutes=1) and not paused and stage != "pidio_persona":
            return "talking", None                      # Nexa respondiendo ahora
        return "waiting", _minutes(last_in, now)
    if last_at and now - last_at <= ACTIVE:
        return "talking", None
    if demo_at and demo_at >= now - timedelta(hours=1):
        return "demo", None
    if stage == "demo_agendada" and demo_at:
        return "demo", None
    return "idle", None


def prospect_state(now: datetime, *, replied_at: Any, opened_at: Any, demo_at: Any, answered_at: Any) -> tuple[str, Optional[int]]:
    replied_at, opened_at, demo_at, answered_at = map(_aware, (replied_at, opened_at, demo_at, answered_at))
    if demo_at and demo_at >= now - timedelta(hours=1):
        return "demo", None
    if replied_at and not (answered_at and answered_at >= replied_at):
        return "waiting", _minutes(replied_at, now)
    return "idle", None


def n8n_state(now: datetime, item: dict) -> tuple[str, Optional[int]]:
    at = _aware(item.get("at"))
    st = str(item.get("state") or "").lower()
    if st in ("respondido", "enviado", "descartado", "ignorado"):
        return "idle", None
    if at and now - at <= JUST_ARRIVED:
        return "new", None
    return "waiting", _minutes(at, now)


def visitor_tag(v: dict) -> dict:
    """Etiqueta: '<tipo de negocio> · <zona>' y '<tema> · <canal> · <estado>'. Nunca datos personales."""
    head = " · ".join(x for x in (v.get("business"), v.get("zone")) if x)
    st = v["state"]
    tail = {"waiting": f"espera {v['wait_min']} min" if v.get("wait_min") is not None else "en espera",
            "demo": f"Demo agendada {v['demo']}" if v.get("demo") else "Demo agendada",
            "talking": "con Nexa", "new": "recién llegado", "idle": v.get("idle_text") or "sin respuesta aún"}[st]
    return {"head": head, "small": " · ".join(x for x in (v.get("topic"), v.get("channel"), tail) if x), "color": COLOR[st]}


def screen_rows(visitors: list[dict]) -> list[dict]:
    out = []
    for v in visitors:
        st = v["state"]
        right = {"waiting": f"En espera · {v['wait_min']} min" if v.get("wait_min") is not None else "En espera",
                 "demo": f"Demo agendada {v['demo']}" if v.get("demo") else "Demo agendada",
                 "idle": "Sin respuesta aún" if v.get("kind") != "landing" else "Abrió la landing"}.get(st, STATE_LABEL[st])
        out.append({"a": " · ".join(x for x in (v.get("business"), v.get("zone")) if x), "b": " · ".join(x for x in (v.get("topic"), v.get("channel")) if x),
                    "state": right, "color": COLOR[st]})
    return out


def arrange(visitors: list[dict], limit: int = VISIBLE) -> dict:
    """Orden: hablando, recien llegados, en espera, demos, sin respuesta; luego lo mas reciente. Maximo 8 + '+N'."""
    vs = sorted(visitors, key=lambda v: (ORDER[v["state"]], -(_aware(v.get("at")) or datetime.min.replace(tzinfo=timezone.utc)).timestamp()))
    shown = vs[:limit]
    talking = next((v for v in shown if v["state"] in ("talking", "new")), None)
    nexa = {"state": "talking" if talking else "idle",
            "text": f"Atendiendo: {talking['topic'].lower() if talking.get('topic') else 'una visita'}" if talking else ("Esperando visitas" if not vs else "Sin conversación activa")}
    return {"visitors": [{**v, "tag": visitor_tag(v)} for v in shown], "interesados": len(vs), "plus": max(0, len(vs) - limit),
            "screen": screen_rows(shown), "nexa": nexa, "empty": not vs}


# ------------------------------------------------------------------ fuentes
async def _whatsapp(r: od.Reader, now: datetime) -> Optional[list[dict]]:
    rows = await r.rows("""
        SELECT c.id::text AS id, c.business_type, COALESCE(NULLIF(c.zone, ''), c.city) AS city, c.main_pain, c.stage, c.nexa_paused, c.first_message_at, c.last_message_at,
               c.last_inbound_at, c.last_preview, c.demo_at,
               (SELECT m.direction FROM wa_messages m WHERE m.contact_id = c.id ORDER BY m.created_at DESC LIMIT 1) AS last_dir,
               (SELECT max(m.created_at) FROM wa_messages m WHERE m.contact_id = c.id AND m.direction = 'out') AS last_out,
               (SELECT string_agg(left(coalesce(m.body, ''), 200), ' ') FROM (SELECT body FROM wa_messages
                  WHERE contact_id = c.id AND direction = 'in' AND created_at >= :s ORDER BY created_at DESC LIMIT 6) m) AS recent_in
        FROM wa_contacts c
        WHERE c.stage NOT IN ('no_interesado', 'baja')
          AND (c.last_message_at >= :s OR c.first_message_at >= :s OR (c.demo_at >= :d0 AND c.demo_at < :d1))
        ORDER BY c.last_message_at DESC NULLS LAST LIMIT 60
    """, {"s": now - WINDOW, "d0": now - timedelta(hours=1), "d1": now + timedelta(days=7)}, tables=("wa_contacts", "wa_messages"))
    if rows is None:
        return None
    out = []
    for x in rows:
        st, wait = wa_state(now, first_at=x["first_message_at"], last_at=x["last_message_at"], last_dir=x["last_dir"], last_in=x["last_inbound_at"],
                            last_out=x["last_out"], demo_at=x["demo_at"], stage=x["stage"] or "", paused=bool(x["nexa_paused"]))
        keys = topic_keys(x.get("main_pain"), x.get("recent_in"), x.get("business_type"))
        out.append({"id": vid("wa", x["id"]), "kind": "wa", "state": st, "wait_min": wait, "demo": demo_label(_aware(x["demo_at"])) if st == "demo" else None,
                    "business": business_label(x.get("business_type")), "zone": scrub(x.get("city"), 22) or None, "topic": topic_label(keys),
                    "channel": "WhatsApp", "at": (_aware(x["last_message_at"]) or now).isoformat(), "link": {"type": "nexa", "id": x["id"]}, "_wa": x["id"]})
    return out


async def _prospects(r: od.Reader, now: datetime, wa_ids: set[str]) -> Optional[list[dict]]:
    rows = await r.rows("""
        SELECT p.id::text AS id, p.name, p.business_type, p.neighborhood, p.locality, z.name AS zone, p.replied_at, p.opened_at, p.demo_at,
               p.wa_contact_id,
               (SELECT max(pc.sent_at) FROM prospect_contacts pc WHERE pc.prospect_id = p.id AND pc.kind ILIKE '%respuesta%') AS answered_at
        FROM prospects p LEFT JOIN prospect_zones z ON z.id = p.zone_id
        WHERE NOT p.is_test AND p.status <> 'baja' AND p.unsubscribed_at IS NULL
          AND (p.replied_at >= :s OR p.opened_at >= :s OR (p.demo_at >= :d0 AND p.demo_at < :d1))
        ORDER BY GREATEST(p.replied_at, p.opened_at, p.demo_at) DESC NULLS LAST LIMIT 60
    """, {"s": now - WINDOW, "d0": now - timedelta(hours=1), "d1": now + timedelta(days=7)}, tables=("prospects", "prospect_zones", "prospect_contacts"))
    if rows is None:
        return None
    out = []
    for x in rows:
        if x.get("wa_contact_id") and x["wa_contact_id"] in wa_ids:
            continue                                   # ya esta en la recepcion por su conversacion de WhatsApp
        st, wait = prospect_state(now, replied_at=x["replied_at"], opened_at=x["opened_at"], demo_at=x["demo_at"], answered_at=x["answered_at"])
        replied = _aware(x["replied_at"]) and _aware(x["replied_at"]) >= now - WINDOW
        btype = PROSPECT_TYPE.get(str(x.get("business_type") or "").lower(), business_label(x.get("business_type")))
        name = scrub(x.get("name"), 22)
        at = max([d for d in map(_aware, (x["replied_at"], x["opened_at"])) if d] or [now])
        out.append({"id": vid("prospecto", x["id"]), "kind": "prospecto" if replied else "landing", "state": st, "wait_min": wait,
                    "demo": demo_label(_aware(x["demo_at"])) if st == "demo" else None,
                    "business": f"{btype} {name}".strip() if name else btype, "zone": scrub(x.get("neighborhood") or x.get("zone") or x.get("locality"), 22) or None,
                    "topic": "Respondió el correo" if replied else "Abrió la landing", "channel": "Correo · prospección" if replied else "Prospección",
                    "idle_text": "abrió la landing" if not replied else "respondido", "at": at.isoformat(), "link": {"type": "mapa", "id": x["id"]}})
    return out


def _n8n_items(now: datetime, n8n: dict) -> tuple[Optional[list[dict]], Optional[list[dict]]]:
    rec = (n8n or {}).get("reception") if (n8n or {}).get("ok") else None
    if not isinstance(rec, dict):
        return None, None
    def build(items: Any, kind: str) -> Optional[list[dict]]:
        if not isinstance(items, list):
            return None
        out = []
        for i, it in enumerate(items[:60]):
            if not isinstance(it, dict):
                continue
            at = _aware(it.get("at"))
            if not at or now - at > WINDOW:
                continue
            st, wait = n8n_state(now, it)
            keys = [k for k in (it.get("topics") or []) if k in TOPIC_LABEL]
            net = str(it.get("channel") or "").lower()
            channel = "Correo" if kind == "correo" else ("Instagram · DEMO" if net == "instagram" else "Facebook · DEMO" if net == "facebook" else "Redes · DEMO")
            out.append({"id": vid(kind, it.get("ref") or f"{at.isoformat()}:{i}"), "kind": kind, "state": st, "wait_min": wait, "demo": None,
                        "business": "Interesado", "zone": None, "topic": topic_label(keys), "channel": channel, "idle_text": "respondido",
                        "at": at.isoformat(), "link": None})
        return out
    return build(rec.get("leads"), "demo"), build(rec.get("mail"), "correo")


async def live_recepcion(r: od.Reader, now: datetime, n8n: dict) -> dict:
    wa = await _whatsapp(r, now)
    wa_ids = {v.pop("_wa") for v in (wa or [])}
    pr = await _prospects(r, now, wa_ids)
    leads, mail = _n8n_items(now, n8n)
    visitors = [*(wa or []), *(pr or []), *(leads or []), *(mail or [])]
    snap = arrange(visitors)
    demos = sum(1 for v in visitors if v["state"] == "demo")
    snap.update(ok=True, template="recepcion", generated_at=now.isoformat(),
                sources={"whatsapp": None if wa is None else len(wa), "prospeccion": None if pr is None else len(pr),
                         "leads_demo": None if leads is None else len(leads), "correos": None if mail is None else len(mail), "demos": demos})
    snap = ov.without_money(snap)
    snap["rev"] = ov.rev({k: v for k, v in snap.items() if k != "generated_at"})
    return snap


__all__ = ["live_recepcion", "wa_state", "prospect_state", "n8n_state", "arrange", "visitor_tag", "screen_rows", "topic_keys", "topic_label",
           "business_label", "scrub", "demo_label"]
