"""Nexa por WhatsApp (API oficial de Meta): la logica compartida.

Meta -> POST /api/v1/nexa-wa/webhook (firma X-Hub-Signature-256) -> aqui se
guarda el mensaje (sin duplicados por id de Meta) y, si el contacto no tiene
Nexa pausada ni esta de baja, se reenvia a n8n con X-Nexa-Forward. n8n decide
la respuesta con Claude, la envia por la Cloud API y la registra en
POST /api/v1/nexa-wa/outbound.

Es de la propia Clonexa (sin company_id, ningun tenant). Solo texto: fotos,
audios y videos no se descargan. Nunca se registran ni devuelven secretos.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
import unicodedata
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("clonexa.nexa_wa")

BOGOTA = timezone(timedelta(hours=-5))  # Colombia no tiene horario de verano
GRAPH_VERSION = "v26.0"
DEFAULT_PHONE_ID = "1331771733361816"
DEFAULT_N8N_URL = "https://main-production-54df.up.railway.app/webhook/nexa-wa-ventas"
DEFAULT_CONSOLE = "https://clonexa-backend-production.up.railway.app/admin-v2plus"

STAGES = ("nuevo", "calificado", "demo_agendada", "pidio_persona", "no_interesado", "baja")
STAGE_LABELS = {"nuevo": "Nuevo", "calificado": "Calificado", "demo_agendada": "Demo agendada", "pidio_persona": "Pidió persona",
                "no_interesado": "No interesado", "baja": "Baja"}
STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}
HISTORY = 20
PER_NUMBER_LIMIT = 20  # mensajes por minuto por numero

OPT_OUT_CONFIRM = {
    "es": "Listo, te dimos de baja: Nexa no te volverá a escribir. Gracias por avisarnos.",
    "en": "Done, you're unsubscribed: Nexa won't message you again. Thanks for letting us know.",
}
FALLBACK = {"es": "Ya te respondemos en un momento.", "en": "We'll get back to you in a moment."}


# ---------------------------------------------------------------- configuracion
def env(name: str) -> str:
    return os.getenv(name, "").strip()


def phone_id() -> str:
    return env("WA_PHONE_NUMBER_ID") or DEFAULT_PHONE_ID


def n8n_url() -> str:
    return env("NEXA_WA_N8N_URL") or DEFAULT_N8N_URL


def console_url(contact_id: str) -> str:
    return f"{env('NEXA_WA_CONSOLE_URL') or DEFAULT_CONSOLE}#nexa/{contact_id}"


def same_secret(given: str, expected: str) -> bool:
    return bool(given) and bool(expected) and hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def signature_ok(body: bytes, header: str, secret: str) -> bool:
    """X-Hub-Signature-256 = 'sha256=' + HMAC-SHA256(cuerpo crudo, clave de la app)."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.strip().lower().encode("utf-8"), expected.encode("utf-8"))


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- limite por numero (un solo worker)
class RateLimit:
    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, at: Optional[float] = None) -> bool:
        at = time.monotonic() if at is None else at
        q = self.hits[key]
        while q and at - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(at)
        if len(self.hits) > 5000:
            for k in [k for k, v in list(self.hits.items()) if not v][:2500]:
                self.hits.pop(k, None)
        return True


PER_NUMBER = RateLimit(PER_NUMBER_LIMIT, 60.0)


# ---------------------------------------------------------------- "baja"
def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]+", " ", value)).strip()


_OPT_OUT_WORDS = {"baja", "stop", "parar", "detener", "alto", "unsubscribe", "cancelar", "darme de baja", "dar de baja", "de baja",
                  "stop please", "stop por favor", "baja por favor", "quiero la baja"}
_OPT_OUT_PHRASES = ("no me escriban", "no me escribas", "no me escriba", "no me vuelvan a escribir", "no me vuelvas a escribir",
                    "dejen de escribir", "deja de escribir", "dejen de escribirme", "deja de escribirme", "no quiero mas mensajes",
                    "no quiero recibir mensajes", "no me manden mensajes", "no me envien mensajes", "no me contacten",
                    "darme de baja", "dame de baja", "denme de baja", "quiero darme de baja", "eliminen mi numero", "borren mi numero",
                    "stop messaging", "stop texting", "do not message", "dont message", "do not contact", "dont contact",
                    "remove me", "unsubscribe me")


def is_opt_out(value: str) -> bool:
    plain = _plain(value)
    if not plain or len(plain) > 160:
        return False
    return plain in _OPT_OUT_WORDS or any(p in plain for p in _OPT_OUT_PHRASES)


# ---------------------------------------------------------------- lectura del webhook de Meta
def _clip(value: Any, limit: int) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value[:limit] or None


def parse_message(m: dict) -> dict:
    """Un mensaje de Meta -> lo que se guarda. Texto, botones y listas tienen texto;
    lo demas (audio, foto, video, sticker...) solo su tipo."""
    kind = str(m.get("type") or "unknown")[:30]
    body, reply_id = None, None
    if kind == "text":
        body = (m.get("text") or {}).get("body")
    elif kind == "interactive":
        inter = m.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        body, reply_id = reply.get("title"), reply.get("id")
    elif kind == "button":
        btn = m.get("button") or {}
        body, reply_id = btn.get("text"), btn.get("payload")
    elif kind in ("image", "video", "document"):
        body = (m.get(kind) or {}).get("caption")
    elif kind == "reaction":
        body = (m.get("reaction") or {}).get("emoji")
    ts = None
    try:
        ts = datetime.fromtimestamp(int(m.get("timestamp")), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        ts = None
    return {"meta_id": _clip(m.get("id"), 200), "wa_id": _clip(m.get("from"), 32), "type": kind,
            "text": _clip(body, 4096), "reply_id": _clip(reply_id, 256), "at": ts}


def iter_changes(payload: dict):
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            if (change or {}).get("field") == "messages" and isinstance(change.get("value"), dict):
                yield change["value"]


def is_answerable(kind: str) -> bool:
    return kind in ("text", "interactive", "button")


# ---------------------------------------------------------------- base de datos
CONTACT_COLS = """id::text AS id, wa_id, profile_name, language, business_type, city, size, main_pain, email, stage, stage_at,
    nexa_paused, consent_seen, first_message_at, last_message_at, last_inbound_at, last_preview, demo_at, demo_link, notes,
    admin_seen_at, created_at"""


async def upsert_contact(db: AsyncSession, wa_id: str, profile_name: Optional[str]) -> dict:
    row = (await db.execute(text(f"""
        INSERT INTO wa_contacts (wa_id, profile_name, stage_at) VALUES (:wa, :name, now())
        ON CONFLICT (wa_id) DO UPDATE SET profile_name = COALESCE(EXCLUDED.profile_name, wa_contacts.profile_name), updated_at = now()
        RETURNING {CONTACT_COLS}
    """), {"wa": wa_id, "name": profile_name})).mappings().first()
    return dict(row)


async def contact_by_wa(db: AsyncSession, wa_id: str) -> Optional[dict]:
    row = (await db.execute(text(f"SELECT {CONTACT_COLS} FROM wa_contacts WHERE wa_id = :wa"), {"wa": wa_id})).mappings().first()
    return dict(row) if row else None


async def contact_by_id(db: AsyncSession, contact_id: str) -> Optional[dict]:
    row = (await db.execute(text(f"SELECT {CONTACT_COLS} FROM wa_contacts WHERE id = CAST(:id AS uuid)"), {"id": contact_id})).mappings().first()
    return dict(row) if row else None


async def insert_message(db: AsyncSession, contact_id: str, *, direction: str, meta_id: Optional[str], kind: str, body: Optional[str],
                         reply_id: Optional[str] = None, options: Any = None, status: Optional[str] = None, error: Optional[str] = None,
                         raw: Optional[dict] = None, at: Optional[datetime] = None) -> Optional[str]:
    """None si el id de Meta ya estaba (duplicado)."""
    row = (await db.execute(text("""
        INSERT INTO wa_messages (meta_id, contact_id, direction, msg_type, body, reply_id, options, status, error, raw, created_at, status_at)
        VALUES (:meta, CAST(:cid AS uuid), :dir, :kind, :body, :reply, CAST(:opts AS jsonb), :status, :error, CAST(:raw AS jsonb),
                COALESCE(:at, now()), CASE WHEN CAST(:status AS varchar) IS NULL THEN NULL ELSE now() END)
        ON CONFLICT (meta_id) DO NOTHING
        RETURNING id::text
    """), {"meta": meta_id, "cid": contact_id, "dir": direction, "kind": kind, "body": body, "reply": reply_id,
           "opts": json.dumps(options) if options is not None else None, "status": status, "error": _clip(error, 500),
           "raw": json.dumps(raw or {}), "at": at})).scalar()
    return row


async def touch_contact(db: AsyncSession, contact_id: str, *, inbound: bool, preview: Optional[str], at: Optional[datetime] = None) -> None:
    await db.execute(text("""
        UPDATE wa_contacts SET
            first_message_at = COALESCE(first_message_at, COALESCE(:at, now())),
            last_message_at = GREATEST(COALESCE(last_message_at, 'epoch'::timestamptz), COALESCE(:at, now())),
            last_inbound_at = CASE WHEN :inbound THEN GREATEST(COALESCE(last_inbound_at, 'epoch'::timestamptz), COALESCE(:at, now())) ELSE last_inbound_at END,
            last_preview = COALESCE(:preview, last_preview),
            updated_at = now()
        WHERE id = CAST(:id AS uuid)
    """), {"id": contact_id, "inbound": inbound, "preview": _clip(preview, 300), "at": at})


def _rank_sql(column: str) -> str:
    cases = " ".join(f"WHEN '{k}' THEN {v}" for k, v in STATUS_RANK.items())
    return f"(CASE {column} {cases} ELSE 0 END)"


async def save_status(db: AsyncSession, st: dict) -> bool:
    """Estado de entrega de un mensaje saliente. Solo avanza (enviado < entregado <
    leido; fallido gana). Si llega antes de que n8n registre el envio, se deja la
    fila lista y el registro de n8n la completa."""
    status = str(st.get("status") or "").lower()
    meta_id = _clip(st.get("id"), 200)
    wa_id = _clip(st.get("recipient_id"), 32)
    if status not in STATUS_RANK or not meta_id:
        return False
    errors = st.get("errors") or []
    error = None
    if errors and isinstance(errors[0], dict):
        error = _clip(f"{errors[0].get('code', '')} {errors[0].get('title') or errors[0].get('message') or ''}", 500)
    updated = (await db.execute(text(f"""
        UPDATE wa_messages SET status = CAST(:status AS varchar), status_at = now(), error = COALESCE(CAST(:error AS varchar), error)
        WHERE meta_id = :meta AND {_rank_sql('CAST(:status AS varchar)')} > {_rank_sql('status')}
        RETURNING id
    """), {"status": status, "meta": meta_id, "error": error})).first()
    if updated:
        return True
    exists = (await db.execute(text("SELECT 1 FROM wa_messages WHERE meta_id = :meta"), {"meta": meta_id})).first()
    if exists or not wa_id:
        return False
    contact = await contact_by_wa(db, wa_id)
    if not contact:
        return False
    await insert_message(db, contact["id"], direction="out", meta_id=meta_id, kind="pendiente", body=None, status=status, error=error,
                         raw={"status": {k: st.get(k) for k in ("id", "status", "timestamp", "recipient_id")}})
    return True


async def history(db: AsyncSession, contact_id: str, limit: int = HISTORY) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT direction, msg_type, body, reply_id, created_at FROM wa_messages
        WHERE contact_id = CAST(:id AS uuid) AND msg_type <> 'pendiente'
        ORDER BY created_at DESC, id DESC LIMIT :n
    """), {"id": contact_id, "n": limit})).mappings().all()
    return [{"direccion": r["direction"], "tipo": r["msg_type"], "texto": r["body"] or "", "reply_id": r["reply_id"],
             "creado": r["created_at"].isoformat() if r["created_at"] else None} for r in reversed(rows)]


async def set_stage(db: AsyncSession, contact_id: str, stage: str) -> None:
    await db.execute(text("""
        UPDATE wa_contacts SET stage = CAST(:stage AS varchar), stage_at = CASE WHEN stage = CAST(:stage AS varchar) THEN stage_at ELSE now() END, updated_at = now()
        WHERE id = CAST(:id AS uuid)
    """), {"id": contact_id, "stage": stage})


def next_stage(current: str, proposed: Optional[str]) -> str:
    """Lo que Nexa detecto no deshace lo ya logrado: baja es final y una demo
    agendada no vuelve a nuevo o calificado."""
    if current == "baja" or proposed not in STAGES or not proposed:
        return current
    if proposed == "nuevo" and current != "nuevo":
        return current
    if current == "demo_agendada" and proposed in ("nuevo", "calificado"):
        return current
    return proposed


def contact_public(c: dict) -> dict:
    iso = lambda v: v.isoformat() if v else None  # noqa: E731
    return {"id": c["id"], "wa_id": c["wa_id"], "nombre": c.get("profile_name"), "idioma": c.get("language"),
            "tipo_negocio": c.get("business_type"), "ciudad": c.get("city"), "tamano": c.get("size"), "dolor": c.get("main_pain"),
            "correo": c.get("email"), "etapa": c.get("stage"), "nexa_pausada": bool(c.get("nexa_paused")),
            "consentimiento_visto": bool(c.get("consent_seen")), "demo_at": iso(c.get("demo_at")), "demo_link": c.get("demo_link"),
            "primer_mensaje_at": iso(c.get("first_message_at")), "ultimo_mensaje_at": iso(c.get("last_message_at")),
            "console_url": console_url(c["id"])}


# ---------------------------------------------------------------- salida (Cloud API y n8n)
async def send_text(wa_id: str, body: str) -> dict:
    """Mensaje de texto por la Cloud API (respuesta dentro de las 24 h). Nunca registra el token."""
    token = env("WA_TOKEN")
    if not token:
        return {"ok": False, "error": "WA_TOKEN no configurado"}
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{phone_id()}/messages"
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": wa_id, "type": "text", "text": {"body": body}}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and data.get("messages"):
            return {"ok": True, "meta_id": data["messages"][0].get("id")}
        err = (data.get("error") or {}) if isinstance(data, dict) else {}
        return {"ok": False, "error": f"{r.status_code} {err.get('code', '')} {err.get('message', '')}"[:300]}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": type(exc).__name__}


async def forward(payload: dict) -> bool:
    """Reenvio a n8n con X-Nexa-Forward; un reintento."""
    secret = env("NEXA_WA_FORWARD_SECRET")
    if not secret:
        log.warning("nexa_wa: NEXA_WA_FORWARD_SECRET no configurado; no se reenvia a n8n")
        return False
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(n8n_url(), json=payload, headers={"X-Nexa-Forward": secret})
            if 200 <= r.status_code < 300:
                return True
            log.warning("nexa_wa: n8n respondio %s (intento %s)", r.status_code, attempt + 1)
        except httpx.HTTPError as exc:
            log.warning("nexa_wa: n8n no respondio (%s, intento %s)", type(exc).__name__, attempt + 1)
        if attempt == 0:
            await asyncio.sleep(1)
    return False


Sender = Callable[[str, str], Awaitable[dict]]
Forwarder = Callable[[dict], Awaitable[bool]]


async def _reply_from_backend(db: AsyncSession, contact: dict, body: str, send: Sender, kind: str = "text") -> None:
    result = await send(contact["wa_id"], body)
    await insert_message(db, contact["id"], direction="out", meta_id=result.get("meta_id"), kind=kind, body=body,
                         status="sent" if result.get("ok") else "failed", error=result.get("error"), raw={"origen": "backend"})
    await touch_contact(db, contact["id"], inbound=False, preview=body)


# ---------------------------------------------------------------- el webhook, en segundo plano
async def process_webhook(db: AsyncSession, payload: dict, *, send: Optional[Sender] = None, fwd: Optional[Forwarder] = None) -> dict:
    send = send or send_text
    fwd = fwd or forward
    out = {"messages": 0, "duplicates": 0, "statuses": 0, "forwarded": 0, "opt_out": 0, "skipped": 0}
    for value in iter_changes(payload):
        names = {}
        for c in value.get("contacts") or []:
            if isinstance(c, dict) and c.get("wa_id"):
                names[str(c["wa_id"])] = _clip((c.get("profile") or {}).get("name"), 200)
        for st in value.get("statuses") or []:
            if isinstance(st, dict) and await save_status(db, st):
                out["statuses"] += 1
        await db.commit()
        for raw in value.get("messages") or []:
            if not isinstance(raw, dict):
                continue
            m = parse_message(raw)
            if not m["meta_id"] or not m["wa_id"]:
                continue
            contact = await upsert_contact(db, m["wa_id"], names.get(m["wa_id"]))
            new_id = await insert_message(db, contact["id"], direction="in", meta_id=m["meta_id"], kind=m["type"], body=m["text"],
                                          reply_id=m["reply_id"], raw=raw, at=m["at"])
            if not new_id:
                out["duplicates"] += 1
                await db.rollback()
                continue
            await touch_contact(db, contact["id"], inbound=True, preview=m["text"] or f"[{m['type']}]", at=m["at"])
            await db.commit()
            out["messages"] += 1
            if contact["stage"] == "baja":
                out["skipped"] += 1
                continue
            if m["type"] == "text" and is_opt_out(m["text"] or ""):
                await set_stage(db, contact["id"], "baja")
                lang = "en" if (contact.get("language") or "").startswith("en") else "es"
                await _reply_from_backend(db, contact, OPT_OUT_CONFIRM[lang], send)
                await db.commit()
                out["opt_out"] += 1
                continue
            if contact["nexa_paused"]:
                out["skipped"] += 1
                continue
            if m["at"] and now() - m["at"] > timedelta(hours=24):
                out["skipped"] += 1  # fuera de la ventana de 24 h: no se responde
                continue
            if not PER_NUMBER.allow(m["wa_id"]):
                log.warning("nexa_wa: limite de %s mensajes por minuto superado por un numero", PER_NUMBER_LIMIT)
                out["skipped"] += 1
                continue
            contact = await contact_by_id(db, contact["id"]) or contact
            body = {
                "mensaje": {"meta_id": m["meta_id"], "tipo": m["type"], "texto": m["text"] or "", "reply_id": m["reply_id"],
                            "respondible": is_answerable(m["type"]), "creado": (m["at"] or now()).isoformat()},
                "contacto": contact_public(contact),
                "historial": await history(db, contact["id"]),
                "primer_mensaje": not contact["consent_seen"],
                "ahora": datetime.now(BOGOTA).isoformat(),
            }
            if await fwd(body):
                out["forwarded"] += 1
            else:
                lang = "en" if (contact.get("language") or "").startswith("en") else "es"
                await _reply_from_backend(db, contact, FALLBACK[lang], send)
                await db.commit()
    return out


# ---------------------------------------------------------------- lo que Nexa envio (n8n)
def _when(value: Any) -> Optional[datetime]:
    try:
        at = datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None
    return at if at and at.tzinfo else None


_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,24}$", re.I)


async def record_outbound(db: AsyncSession, contact: dict, data: dict) -> dict:
    for msg in data.get("mensajes") or []:
        status = msg.get("estado") if msg.get("estado") in STATUS_RANK else ("sent" if msg.get("meta_id") else "failed")
        opts = msg.get("opciones") or None
        new_id = await insert_message(db, contact["id"], direction="out", meta_id=msg.get("meta_id"), kind=msg.get("tipo") or "text",
                                      body=msg.get("texto"), options=opts, status=status, error=msg.get("error"),
                                      raw={"origen": "n8n", "accion": data.get("accion")})
        if not new_id and msg.get("meta_id"):
            # Meta mando el estado antes que n8n el registro: se completa esa fila.
            await db.execute(text("""
                UPDATE wa_messages SET msg_type = :kind, body = :body, options = CAST(:opts AS jsonb), raw = CAST(:raw AS jsonb)
                WHERE meta_id = :meta AND direction = 'out'
            """), {"kind": msg.get("tipo") or "text", "body": msg.get("texto"), "opts": json.dumps(opts) if opts is not None else None,
                   "raw": json.dumps({"origen": "n8n", "accion": data.get("accion")}), "meta": msg["meta_id"]})
        await touch_contact(db, contact["id"], inbound=False, preview=msg.get("texto"))
    d = data.get("datos_detectados") or {}
    email = (d.get("correo") or "").strip()
    demo = data.get("demo") or {}
    await db.execute(text("""
        UPDATE wa_contacts SET
            language = COALESCE(:language, language), business_type = COALESCE(:business, business_type), city = COALESCE(:city, city),
            size = COALESCE(:size, size), main_pain = COALESCE(:pain, main_pain), email = COALESCE(:email, email),
            profile_name = COALESCE(profile_name, :name),
            consent_seen = consent_seen OR :consent,
            demo_at = COALESCE(CAST(:demo_at AS timestamptz), demo_at), demo_link = COALESCE(:demo_link, demo_link),
            notes = CASE WHEN CAST(:note AS text) IS NULL THEN notes ELSE concat_ws(E'\\n', notes, CAST(:note AS text)) END,
            updated_at = now()
        WHERE id = CAST(:id AS uuid)
    """), {"id": contact["id"], "language": _clip(d.get("idioma"), 8), "business": _clip(d.get("tipo_negocio"), 120),
           "city": _clip(d.get("ciudad"), 120), "size": _clip(d.get("tamano"), 200), "pain": _clip(d.get("dolor"), 500),
           "email": email[:254] if _EMAIL.match(email) else None, "name": _clip(d.get("nombre"), 200),
           "consent": bool(data.get("consentimiento_visto")), "demo_at": _when(demo.get("inicio")),
           "demo_link": _clip(demo.get("enlace"), 500), "note": _clip(data.get("nota"), 1000)})
    stage = next_stage(contact["stage"], data.get("etapa"))
    if stage != contact["stage"]:
        await set_stage(db, contact["id"], stage)
    await db.commit()
    return await contact_by_id(db, contact["id"]) or contact


# ---------------------------------------------------------------- resumen diario (6 p. m.)
async def daily_summary(db: AsyncSession, day: Optional[datetime] = None) -> dict:
    today = (day or datetime.now(BOGOTA)).astimezone(BOGOTA).date()
    start = datetime(today.year, today.month, today.day, tzinfo=BOGOTA)
    p = {"start": start, "end": start + timedelta(days=1)}
    row = (await db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE first_message_at >= :start AND first_message_at < :end)::int AS nuevas,
          COUNT(*) FILTER (WHERE stage IN ('calificado', 'demo_agendada') AND stage_at >= :start AND stage_at < :end)::int AS calificadas,
          COUNT(*) FILTER (WHERE stage = 'demo_agendada' AND stage_at >= :start AND stage_at < :end)::int AS demos,
          COUNT(*) FILTER (WHERE stage = 'pidio_persona' AND stage_at >= :start AND stage_at < :end)::int AS personas,
          COUNT(*) FILTER (WHERE last_message_at >= :start AND last_message_at < :end)::int AS activas
        FROM wa_contacts
    """), p)).mappings().first()
    rows = (await db.execute(text(f"""
        SELECT {CONTACT_COLS} FROM wa_contacts WHERE last_message_at >= :start AND last_message_at < :end
        ORDER BY last_message_at DESC LIMIT 10
    """), p)).mappings().all()
    return {"ok": True, "fecha": today.isoformat(), **{k: int(v or 0) for k, v in dict(row).items()},
            "contactos": [contact_public(dict(r)) for r in rows]}
