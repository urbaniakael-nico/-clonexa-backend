"""Oficina 3D · fase 1.5: piso realista, marca de cada empresa y copia viva del bar.

Interno de Clonexa (solo Admin V2 / v2+). Ninguna empresa cliente ve nada nuevo.

- Interruptor por empresa: oficina_pisos.estilo ('clasico' por defecto, 'realista' encendido solo en
  The Time Machine por la migracion 025k). El motor realista esta listo por plantilla (REAL_TEMPLATES);
  hoy solo 'bar' tiene distribucion realista.
- Marca: tema PUBLICADO del Estudio de marca (colores + logo); si no hay, la marca del panel inicial
  (company_branding); si tampoco, paleta neutra y el aviso "Configura la marca en el Estudio de marca".
  Se ajusta el contraste (neon y textos legibles siempre).
- Copia viva: mesas reales (las del QR de mesas), mesas abiertas, pedidos a barra (solo cantidad de
  productos), canciones, juego activo y personal en turno. SOLO actividad: nunca dinero (ni totales, ni
  precios, ni cuentas); without_money() lo garantiza al final. Clientes anonimos.
- Cada consulta filtra por company_id.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from app.services import brand_theme as bt
from app.services import oficina as of

log = logging.getLogger("clonexa.oficina")

STYLES_FLOOR = ("clasico", "realista", "bar", "aprobado")   # "bar": bar aprobado (025l, TTM); "aprobado": 025m
REAL_TEMPLATES = ("bar",)
NEUTRAL = {"primary": "#b08d57", "secondary": "#3b4b5a", "background": "#141519", "surface": "#24262c", "text": "#f2efe9"}
ROOM_DARK = "#0f0c11"
NO_BRAND = "⚠ Configura la marca en el Estudio de marca"
MONEY_RE = re.compile(r"(total|price|precio|subtotal|amount|monto|valor|sales|venta|ticket|cash|dinero|money|cuenta|propina|tip|cost)", re.I)

# ------------------------------------------------------------------ marca
HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _hex(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not HEX.match(raw):
        return None
    return ("#" + raw.lstrip("#")).lower()


def legacy_branding(settings: Any) -> dict:
    """La marca del panel inicial (company_branding) dentro de settings_json, como la lee el portal."""
    if isinstance(settings, str):
        try:
            settings = json.loads(settings or "{}")
        except ValueError:
            settings = {}
    settings = settings if isinstance(settings, dict) else {}
    exp = settings.get("experience") if isinstance(settings.get("experience"), dict) else {}
    for cand in (settings.get("branding"), settings.get("company_branding"), exp.get("branding")):
        if isinstance(cand, dict) and (cand.get("primary_color") or cand.get("logo_url")):
            return cand
    return {}


def readable_accent(color: str, against: str = ROOM_DARK, minimum: float = 3.0) -> str:
    """El color de la marca, aclarado lo justo para que se lea como neon sobre el salon oscuro."""
    out = color
    for step in range(1, 11):
        if bt.contrast(out, against) >= minimum:
            return out
        out = bt.mix(color, "#ffffff", step / 10)
    return out


def palette(tokens: Optional[dict], legacy: Optional[dict]) -> dict:
    """Colores y origen de la marca del piso. Funcion pura (probada)."""
    source, warning = "neutra", NO_BRAND
    colors = dict(NEUTRAL)
    if tokens:
        c = tokens["theme"]["colors"]
        colors = {k: c[k] for k in ("primary", "secondary", "background", "surface", "text")}
        source, warning = "estudio", None
    elif legacy and _hex(legacy.get("primary_color")):
        colors["primary"] = _hex(legacy.get("primary_color"))
        colors["secondary"] = _hex(legacy.get("secondary_color")) or bt.mix(colors["primary"], "#000000", 0.45)
        if _hex(legacy.get("background_color")):
            colors["background"] = _hex(legacy.get("background_color"))
        if _hex(legacy.get("text_color")):
            colors["text"] = _hex(legacy.get("text_color"))
        source, warning = "panel", NO_BRAND
    accent = readable_accent(colors["primary"])
    accent2 = readable_accent(colors["secondary"])
    screen_bg = colors["background"]
    return {"source": source, "warning": warning, "colors": colors, "accent": accent, "accent2": accent2,
            "screen_bg": screen_bg, "screen_text": bt.on_color(screen_bg),
            "uniform": colors["primary"], "uniform2": colors["secondary"], "uniform_text": bt.on_color(colors["primary"])}


def legacy_logo_bytes(legacy: dict) -> Optional[tuple[bytes, str]]:
    """El logo del panel inicial si viene como data:image (PNG/JPG/WebP reales)."""
    logo = str((legacy or {}).get("logo_url") or "")
    if not logo.startswith("data:image/") or ";base64," not in logo:
        return None
    try:
        raw = base64.b64decode(logo.split(";base64,", 1)[1], validate=False)
    except ValueError:
        return None
    sniffed = of.sniff_image(raw)
    return (raw, sniffed[0]) if sniffed else None


async def brand(db, company_id: str, settings: Any) -> dict:
    from app.services import brand_store

    tokens = await brand_store.published_tokens(db, company_id)
    legacy = legacy_branding(settings)
    out = palette(tokens, legacy)
    logo_v = ""
    if tokens and tokens["theme"].get("logo"):
        logo_v = str(tokens["theme"]["logo"])
    elif legacy_logo_bytes(legacy):
        logo_v = hashlib.sha256(str(legacy.get("logo_url")).encode()).hexdigest()[:12]
    out["logo_url"] = f"/admin-v2/api/oficina/marca/{company_id}/logo?v={logo_v}" if logo_v else ""
    return out


async def logo(db, company_id: str, settings: Any) -> Optional[tuple[bytes, str]]:
    from app.services import brand_media, brand_store

    tokens = await brand_store.published_tokens(db, company_id)
    if tokens and tokens["theme"].get("logo"):
        try:
            data = await brand_media.read(db, company_id, tokens["theme"]["logo"])
        except Exception:
            data = None
        if data:
            return data, "image/webp"
    return legacy_logo_bytes(legacy_branding(settings))


# ------------------------------------------------------------------ distribucion (modo arquitecto)
FIXED = ("barra", "dj", "pantalla", "entrada", "caja", "personal")
COLS = 5


def room(tables: int) -> dict:
    rows = max(1, math.ceil(tables / COLS))
    return {"W": 26.0, "D": round(max(18.0, 9.0 + rows * 3.4 + 2.5), 2)}


def auto_layout(tables: list[str]) -> dict:
    """Acomodar automatico: barra y caja al fondo izquierdo, DJ al fondo derecho, pantalla grande en la
    pared del fondo, entrada adelante a la derecha, zona de personal adelante a la izquierda y las mesas en
    cuadricula (5 por fila). Coordenadas [x, z, giro] en metros; la pared del fondo es z = -D/2."""
    rm = room(len(tables))
    W, D = rm["W"], rm["D"]
    items: dict[str, list[float]] = {
        "barra": [-W / 2 + 5.5, -D / 2 + 2.3, 0.0], "caja": [-W / 2 + 11.3, -D / 2 + 2.3, 0.0],
        "dj": [W / 2 - 3.2, -D / 2 + 2.2, 0.0], "pantalla": [3.0, -D / 2 + 0.2, 0.0],
        "entrada": [W / 2 - 2.2, D / 2 - 0.6, 0.0], "personal": [-W / 2 + 2.4, D / 2 - 2.4, 0.0],
    }
    step_x = (W - 6.0) / (COLS - 1)
    for i, label in enumerate(tables):
        r, c = divmod(i, COLS)
        items[f"mesa:{label}"] = [round(-W / 2 + 3.0 + c * step_x + (0.9 if r % 2 else 0.0), 2), round(-D / 2 + 7.2 + r * 3.4, 2), 0.0]
    return {"room": rm, "items": {k: [round(v[0], 2), round(v[1], 2), v[2]] for k, v in items.items()}}


def clean_layout(body: Any, tables: list[str]) -> dict:
    """Lo que manda el modo arquitecto: solo claves conocidas y numeros dentro del salon."""
    if not isinstance(body, dict) or not isinstance(body.get("items"), dict):
        raise of.Rejected("Envía la distribución.")
    allowed = set(FIXED) | {f"mesa:{t}" for t in tables}
    rm = room(len(tables))
    out: dict[str, list[float]] = {}
    if len(body["items"]) > 260:
        raise of.Rejected("Demasiados objetos.")
    for key, value in body["items"].items():
        if key not in allowed:
            raise of.Rejected("La distribución tiene objetos que no son de este piso.")
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise of.Rejected("Posición no válida.")
        try:
            x, z, r = (float(v) for v in value)
        except (TypeError, ValueError):
            raise of.Rejected("Posición no válida.") from None
        if not all(math.isfinite(v) for v in (x, z, r)):
            raise of.Rejected("Posición no válida.")
        out[key] = [round(max(-rm["W"] / 2, min(rm["W"] / 2, x)), 2), round(max(-rm["D"] / 2, min(rm["D"] / 2, z)), 2),
                    round(math.remainder(r, 2 * math.pi), 3)]
    return {"items": out}


def merge_layout(tables: list[str], saved: Any) -> dict:
    """Lo guardado manda; mesas nuevas (y lo que no se guardo) caen en su puesto automatico."""
    auto = auto_layout(tables)
    items = dict(auto["items"])
    stored = (saved or {}).get("items") if isinstance(saved, dict) else None
    moved = 0
    for k, v in (stored or {}).items():
        if k in items and isinstance(v, list) and len(v) == 3:
            items[k] = v
            moved += 1
    return {"room": auto["room"], "items": items, "custom": moved > 0}


# ------------------------------------------------------------------ dia del bar
def business(now: datetime, tz, cfg: Optional[dict], activity: bool) -> dict:
    """Abierto entre la apertura y el cierre (18:00-04:00 por defecto). Fuera de horario: luces bajas y
    letrero, salvo que haya actividad (entonces se muestra igual)."""
    cfg = cfg if cfg and of.clock(cfg.get("open")) and of.clock(cfg.get("close")) else of.BAR_DEFAULT_DAY
    o, c = of.clock(cfg["open"]), of.clock(cfg["close"])
    local = now.astimezone(tz)
    minute = local.hour * 60 + local.minute
    om, cm = o[0] * 60 + o[1], c[0] * 60 + c[1]
    is_open = (minute >= om or minute < cm) if cm < om else (om <= minute < cm)
    sign = f"Cerrado · abre {o[0]:02d}:{o[1]:02d}"
    return {"open": is_open, "lights": "on" if is_open or activity else "low", "sign": None if is_open else sign,
            "activity_off_hours": (not is_open) and activity, "hours": f"{o[0]:02d}:{o[1]:02d}–{c[0]:02d}:{c[1]:02d}"}


# ------------------------------------------------------------------ copia viva
ORDER_STATE = {"pendiente": "nuevo", "alistando": "preparando", "entregado": "entregado"}
GAME_LABEL = {"roulette": "Ruleta", "trivia": "Trivia", "memory": "Memoria"}


def _short(value: Any, size: int = 60) -> str:
    return re.sub(r"[\x00-\x1f<>]", "", str(value or "")).strip()[:size]


def _hid(value: Any) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()[:10]


def table_label(raw_label: Any, raw_key: Any, tables: list[str]) -> str:
    label = _short(raw_label, 40)
    if label in tables:
        return label
    key = _short(raw_key, 40)
    num = re.sub(r"\D", "", label) if label else re.sub(r"\D", "", key)
    if num and f"Mesa {int(num)}" in tables:
        return f"Mesa {int(num)}"
    return label or key or "Mesa"


def tasks(staff: list[dict], orders: list[dict], tables_open: int, song: Optional[str], now: datetime) -> list[dict]:
    """Globo de cada persona en turno con su tarea actual (funcion pura)."""
    queue = sorted([o for o in orders if o["state"] in ("nuevo", "preparando")], key=lambda o: o["at"] or "")
    recent = sorted([o for o in orders if o["state"] == "entregado"], key=lambda o: o["updated_at"] or "", reverse=True)
    barmen = [p for p in staff if p["uniform"] == "barman" and not p["paused"]]
    waiters = [p for p in staff if p["uniform"] in ("mesero", "") and not p["paused"]]
    out = []
    for p in staff:
        task = "Atendiendo"
        if p["paused"]:
            task = "En pausa · café"
        elif p["uniform"] == "barman":
            mine = queue[barmen.index(p)::max(1, len(barmen))] if p in barmen else []
            task = f"Preparando {mine[0]['items']} {'producto' if mine[0]['items'] == 1 else 'productos'} · {mine[0]['table']}" if mine else "Atendiendo la barra"
        elif p["uniform"] in ("mesero", ""):
            mine = recent[waiters.index(p)::max(1, len(waiters))] if p in waiters else []
            fresh = [o for o in mine if (of.parse_dt(o["updated_at"]) or now) >= now - timedelta(minutes=3)]
            task = f"Llevando pedido · {fresh[0]['table']}" if fresh else (f"Atendiendo {tables_open} {'mesa' if tables_open == 1 else 'mesas'}" if tables_open else "Esperando clientes")
        elif p["uniform"] == "dj":
            task = f"Mezclando · {song}" if song else "Mezclando"
        elif p["uniform"] == "caja":
            task = "En caja"
        elif p["uniform"] == "cocina":
            task = "En cocina"
        out.append({**p, "task": task})
    return out


BAR_SEAT = re.compile(r"^(?:barra|bar)(?:$|[\s·:#-])\D*(\d{1,2})?", re.I)


def song_place(raw: Any, tables: list[str]) -> str:
    """Desde donde se pidio una cancion: 'Mesa 4' o 'Barra · silla 3' (nunca el nombre del cliente)."""
    label = _short(raw, 40)
    if not label:
        return ""
    seat = BAR_SEAT.match(label)
    if seat:
        return f"Barra · silla {int(seat.group(1))}" if seat.group(1) else "Barra"
    return table_label(label, "", tables)


def song_screen(items: list[dict]) -> dict:
    """Pantalla "Canciones pedidas" del bar: la que suena (estado 'sonando', la mas reciente) y las siguientes 3
    en cola (pendientes, la mas antigua primero). Funcion pura (probada). Sin pedidas: now = None y queue = []."""
    playing = sorted([s for s in items if s["state"] == "sonando"], key=lambda s: s.get("playing_at") or s.get("at") or "", reverse=True)
    queue = sorted([s for s in items if s["state"] == "pendiente"], key=lambda s: s.get("at") or "")
    now = playing[0] if playing else None
    return {"now": {"title": now["title"], "table": now["table"], "since": now.get("playing_at") or now.get("at")} if now else None,
            "queue": [{"title": s["title"], "table": s["table"]} for s in queue[:3]]}


def rev(snapshot: dict) -> str:
    body = {k: v for k, v in snapshot.items() if k not in ("generated_at", "rev")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]


def without_money(value: Any) -> Any:
    """Quita cualquier campo con nombre de dinero (defensa final: la copia viva es solo actividad)."""
    if isinstance(value, dict):
        return {k: without_money(v) for k, v in value.items() if not MONEY_RE.search(str(k))}
    if isinstance(value, list):
        return [without_money(v) for v in value]
    return value


QTY_SQL = """
    (SELECT COALESCE(SUM(CASE WHEN (x->>'quantity') ~ '^[0-9]+(\\.[0-9]+)?$' THEN CEIL((x->>'quantity')::numeric) ELSE 1 END), 0)
     FROM jsonb_array_elements(CASE WHEN jsonb_typeof(o.items) = 'array' THEN o.items ELSE '[]'::jsonb END) x)
"""


async def live(r, c: dict, now: datetime, privacy: str, saved_layout: Any) -> dict:
    """La copia viva de un bar: distribucion + estado. r = oficina_data.Reader; c = empresa registrada."""
    from app.services import carta_links
    from app.services import oficina_data as od

    cid = c["id"]
    tz = od._zone(c.get("timezone"))
    try:
        tables = await carta_links.mesa_labels(r.db, cid)
    except Exception as error:
        log.warning("oficina: mesas sin datos (%s)", type(error).__name__)
        await r.db.rollback()
        tables = [f"Mesa {i}" for i in range(1, 13)]
    since = now - timedelta(hours=12)
    access = await r.rows("""
        SELECT a.id::text AS id, a.table_key, COALESCE(a.table_number, '') AS table_number, a.activated_at,
               (SELECT COUNT(*) FROM hospitality_table_guests g WHERE g.company_id = a.company_id AND g.access_id = a.id) AS guests
        FROM hospitality_table_access a
        WHERE a.company_id = CAST(:c AS uuid) AND lower(COALESCE(a.status, '')) = 'active' AND (a.expires_at IS NULL OR a.expires_at > :n)
    """, {"c": cid, "n": now}, tables=("hospitality_table_access", "hospitality_table_guests"))
    orders_raw = await r.rows(f"""
        SELECT o.id::text AS id, COALESCE(o.table_key, '') AS table_key, COALESCE(o.table_number, '') AS table_number,
               lower(o.status) AS status, o.created_at, COALESCE(o.updated_at, o.created_at) AS updated_at, {QTY_SQL} AS items
        FROM hospitality_orders o
        WHERE o.company_id = CAST(:c AS uuid) AND o.created_at >= :s AND o.archived_at IS NULL AND o.cancelled_at IS NULL
          AND lower(COALESCE(o.order_type, 'table')) <> 'domicilio' AND lower(o.status) = ANY(:a)
        ORDER BY o.created_at
    """, {"c": cid, "s": since, "a": list(ORDER_STATE)}, tables=("hospitality_orders",))
    songs = await r.rows("""
        SELECT id::text AS id, COALESCE(song, '') AS song, lower(COALESCE(status, '')) AS status, created_at,
               COALESCE(table_number, '') AS table_number, playing_at
        FROM hospitality_song_requests
        WHERE company_id = CAST(:c AS uuid) AND created_at >= :s AND archived_at IS NULL
          AND lower(COALESCE(status, '')) IN ('pendiente', 'sonando', 'reproducida')
        ORDER BY created_at DESC LIMIT 20
    """, {"c": cid, "s": now - timedelta(hours=4)}, tables=("hospitality_song_requests",))
    game = await r.one("""
        SELECT kind, status, started_at, ends_at FROM loyalty_game_rounds
        WHERE company_id = CAST(:c AS uuid) AND status IN ('registration', 'playing') AND created_at >= :s
        ORDER BY created_at DESC LIMIT 1
    """, {"c": cid, "s": now - timedelta(hours=12)}, tables=("loyalty_game_rounds",))
    shifts = await od.open_shifts(r, cid, now)

    orders = []
    for o in orders_raw or []:
        label = table_label(o["table_number"], o["table_key"], tables)
        orders.append({"id": _hid(o["id"]), "table": label, "state": ORDER_STATE[o["status"]], "items": max(1, int(o["items"] or 0)),
                       "at": of.iso(o["created_at"]), "updated_at": of.iso(o["updated_at"])})
    open_tables: dict[str, dict] = {}
    for a in access or []:
        label = table_label(a["table_number"], a["table_key"], tables)
        open_tables[label] = {"since": of.iso(a["activated_at"]), "guests": int(a["guests"] or 0) or None}
    for o in orders:
        open_tables.setdefault(o["table"], {"since": o["at"], "guests": None})
    extra = [t for t in open_tables if t not in tables]
    all_tables = tables + sorted(extra)
    song_items = [{"id": _hid(s["id"]), "title": _short(s["song"]), "state": s["status"], "at": of.iso(s["created_at"]),
                   "table": song_place(s.get("table_number"), tables), "playing_at": of.iso(s.get("playing_at"))}
                  for s in songs or [] if _short(s["song"])]
    staff = of.staff_out(shifts or [], "bar", privacy) if shifts is not None else {"total": None, "visible": [], "extra": 0}
    people = tasks([{k: p[k] for k in ("key", "label", "role", "uniform", "paused")} for p in staff["visible"]], orders,
                   len(open_tables), song_items[0]["title"] if song_items else None, now)
    activity = bool(open_tables or orders or (staff.get("total") or 0))
    kpis, _lines = await od.bar_kpis(r, c, now, shifts)
    brand_out = await brand(r.db, cid, c.get("settings"))
    snap = {
        "ok": True, "company_id": cid, "template": "bar",
        "layout": merge_layout(all_tables, saved_layout),
        "tables": [{"label": t, "open": t in open_tables, **(open_tables.get(t) or {"since": None, "guests": None})} for t in all_tables],
        "orders": orders, "songs": song_items[:6], "song_screen": song_screen(song_items),
        "game": {"kind": game["kind"], "label": GAME_LABEL.get(game["kind"], game["kind"]), "state": game["status"],
                 "ends_at": of.iso(game.get("ends_at"))} if game else None,
        "staff": {"count": staff.get("total"), "extra": staff.get("extra", 0), "people": people},
        "business": business(now, tz, c.get("business_day"), activity),
        "kpis": kpis, "brand": brand_out,
        "known": {"tables_open": access is not None, "orders": orders_raw is not None, "songs": songs is not None,
                  "game": game is not None, "staff": shifts is not None},
    }
    snap = without_money(snap)
    snap["rev"] = rev(snap)
    snap["generated_at"] = now.isoformat()
    return snap
