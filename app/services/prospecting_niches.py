"""Nichos, canales publicos, vigencia, textos de la cola asistida, ruta de visitas y costos de la prospeccion
de Nexa. Puro: no toca la base (lo usa app/services/prospecting.py). Interno de Clonexa.

Reglas que viven aqui:
- Cada tipo de negocio pertenece a un nicho; cada nicho tiene su pagina de la landing (o la principal con
  #seccion si la pagina no existe: NO se inventan paginas), su prioridad y su volante.
- Canales: solo lo que el negocio PUBLICA (ficha de Google y su web). Se guarda la URL de donde salio cada dato.
  Enlaces de compartir, publicaciones sueltas y cuentas de plataformas no cuentan.
- Vigencia (regla inicial): sin actividad visible en 12 meses -> "por_verificar" (no entra a correo ni a la
  cola asistida; solo a la ruta de visitas).
- Textos: plantillas con variables, sin precios, siempre con la opcion de no recibir mas mensajes. Sin Claude
  (costo de tokens = 0).
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import parse_qs, quote, urlencode, urlparse

# ---------------------------------------------------------------- nichos
NICHES: dict[str, dict[str, Any]] = {
    "restaurante": {"label": "Restaurantes y comidas", "priority": 0, "page": "restaurantes", "anchor": "#carta-video",
                    "icon": "🍽️", "color": "#f59e0b", "flyer": "restaurante"},
    "taller": {"label": "Talleres y fábricas", "priority": 1, "page": "talleres-y-fabricas", "anchor": "",
               "icon": "🧵", "color": "#ff2d6f", "flyer": "taller"},
    "campo": {"label": "Empresas de campo", "priority": 1, "page": "personal-en-campo", "anchor": "",
              "icon": "🦺", "color": "#22c55e", "flyer": "campo"},
    "transporte": {"label": "Transporte y logística", "priority": 2, "page": "", "anchor": "#soluciones",
                   "icon": "🚚", "color": "#3b82f6", "flyer": "campo"},
    "tienda": {"label": "Tiendas y minimercados", "priority": 2, "page": "", "anchor": "#soluciones",
               "icon": "🛒", "color": "#14b8a6", "flyer": "tienda"},
    "bar": {"label": "Bares", "priority": 2, "page": "bares", "anchor": "", "icon": "🍸", "color": "#a855f7", "flyer": "bar"},
}
FLYERS = ("restaurante", "bar", "taller", "campo", "tienda")
MISSING_PAGES = {k: v["label"] for k, v in NICHES.items() if not v["page"]}

# tipo -> (nicho, etiqueta, busqueda en Google, includedType o None)
TYPE_DEFS: dict[str, tuple[str, str, str, Optional[str]]] = {
    "restaurante": ("restaurante", "Restaurante", "restaurantes", "restaurant"),
    "comidas_rapidas": ("restaurante", "Comidas rápidas", "comidas rápidas", "fast_food_restaurant"),
    "cafe": ("restaurante", "Café", "cafeterías", "cafe"),
    "panaderia": ("restaurante", "Panadería", "panaderías", "bakery"),
    "bar": ("bar", "Bar", "bares", "bar"),
    "taller": ("taller", "Taller de confección", "taller de confección", None),
    "fabrica": ("taller", "Fábrica pequeña", "fábrica de confecciones", None),
    "electrico": ("campo", "Contratista eléctrico", "contratista eléctrico", "electrician"),
    "telecom": ("campo", "Telecomunicaciones", "empresa instaladora de redes y telecomunicaciones", None),
    "construccion": ("campo", "Construcción", "contratista de construcción y obra", "general_contractor"),
    "instalador": ("campo", "Instaladores", "empresa de instalaciones drywall gas cámaras", None),
    "aseo": ("campo", "Aseo", "empresa de aseo y limpieza", None),
    "vigilancia": ("campo", "Vigilancia", "empresa de vigilancia y seguridad privada", None),
    "transporte": ("transporte", "Transporte y logística", "empresa de transporte y logística", None),
    "tienda": ("tienda", "Tienda / minimercado", "minimercado", None),
}
TYPES = tuple(TYPE_DEFS)
TYPE_LABEL = {k: v[1] for k, v in TYPE_DEFS.items()}
SEARCH = {k: (v[2], v[3]) for k, v in TYPE_DEFS.items()}
# lo que se buscaba antes de 025p en las zonas sin nichos (Kennedy, Techo, Hipotecho): no cambia
LEGACY_TYPES = ("restaurante", "comidas_rapidas", "cafe", "panaderia", "bar", "taller")
TYPE_SLUG = {k: k.replace("_", "-") for k in TYPE_DEFS}

# 34 busquedas al dia como maximo (x 22 dias habiles = ~750 al mes: dentro de las 1.000 gratis de Text Search Enterprise)
DEFAULT_SEARCH_LIMITS = {"restaurante": 8, "taller": 8, "campo": 12, "transporte": 2, "tienda": 2, "bar": 2}
DAILY_MAX_SEARCHES = 34
DEFAULT_ZONE_LIMIT = 6


def niche_of(business_type: str) -> str:
    return TYPE_DEFS.get(business_type, ("restaurante",))[0]


def types_of(niche: str) -> list[str]:
    return [k for k, v in TYPE_DEFS.items() if v[0] == niche]


def zone_types(zone: dict) -> list[str]:
    ns = [n for n in (zone.get("niches") or []) if n in NICHES]
    if not ns:
        return list(LEGACY_TYPES)
    return [t for n in ns for t in types_of(n)]


def priority(niche: str) -> int:
    p = NICHES.get(niche, {}).get("priority", 3)
    return 1 if p == 0 else p   # restaurantes en sus zonas de siempre van con la prioridad 1


def landing_url(landing: str, niche: str, query: dict) -> str:
    n = NICHES.get(niche) or NICHES["restaurante"]
    base = (landing or "https://www.clonexa.com.co/").rstrip("/") + "/"
    return f"{base}{n['page']}?{urlencode(query)}{n['anchor']}"


def campaign(zone_slug: str, business_type: str) -> str:
    return f"{zone_slug or 'sin-zona'}-{TYPE_SLUG.get(business_type, business_type or 'negocio')}"


def flyer_url(landing: str, zone_slug: str, niche: str) -> str:
    """QR del volante: por ZONA y nicho (no por negocio)."""
    return landing_url(landing, niche, {"utm_source": "volante", "utm_medium": "volante",
                                        "utm_campaign": f"{zone_slug}-{niche}"})


def parse_flyer_campaign(value: str) -> tuple[str, str]:
    v = (value or "").strip().lower()
    for n in NICHES:
        if v.endswith("-" + n):
            return v[: -len(n) - 1], n
    return v, ""


# ---------------------------------------------------------------- canales publicos
_IG_RESERVED = {"p", "reel", "reels", "explore", "stories", "accounts", "tv", "share", "direct", "about", "developer",
                "legal", "web", "instagram", "privacy"}
_FB_RESERVED = {"sharer", "sharer.php", "share", "share.php", "dialog", "plugins", "tr", "login", "login.php", "groups",
                "events", "watch", "hashtag", "help", "policies", "privacy", "facebook", "photo", "photo.php", "story.php",
                "permalink.php", "home.php", "marketplace", "gaming", "business", "ads", "l.php", "people", "media"}
_TT_RESERVED = {"tiktok", "share"}
OWN_HANDLES = {"clonexaapp", "clonexa", "clonexasaas"}
HREF_ANY = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
URL_ANY = re.compile(r"""https?://[^\s"'<>()]+""", re.I)


def _host(url: str) -> str:
    try:
        h = (urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
    except ValueError:
        return ""
    for p in ("www.", "m.", "mobile.", "web.", "es-la.", "es.", "business."):
        if h.startswith(p):
            h = h[len(p):]
    return h


def _digits(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def classify_link(url: str) -> Optional[tuple[str, str, str]]:
    """(red, valor, url_limpia) para un enlace a un perfil publico; None si no es un perfil."""
    raw = (url or "").strip()
    if not raw or raw.startswith(("mailto:", "tel:", "#", "javascript:")):
        return None
    if raw.lower().startswith("whatsapp://"):
        q = parse_qs(urlparse(raw).query)
        num = _digits((q.get("phone") or [""])[0])
        return ("whatsapp", num, f"https://wa.me/{num}") if 8 <= len(num) <= 15 else None
    try:
        parsed = urlparse(raw if "://" in raw else "https://" + raw)
    except ValueError:
        return None
    host = _host(raw)
    parts = [p for p in (parsed.path or "").split("/") if p]
    if host == "instagram.com":
        if not parts or parts[0].lower() in _IG_RESERVED:
            return None
        handle = parts[0].lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9_.]{2,30}", handle) or handle.lower() in OWN_HANDLES:
            return None
        return "instagram", "@" + handle.lower(), f"https://www.instagram.com/{handle.lower()}/"
    if host in ("facebook.com", "fb.com", "fb.me"):
        if not parts:
            return None
        first = parts[0].lower()
        if first == "profile.php":
            pid = _digits((parse_qs(parsed.query).get("id") or [""])[0])
            return ("facebook", pid, f"https://www.facebook.com/profile.php?id={pid}") if pid else None
        if first == "pages" and len(parts) >= 2:
            slug = "/".join(parts[1:3])
            return "facebook", slug.lower(), f"https://www.facebook.com/pages/{slug}"
        if first in _FB_RESERVED or not re.fullmatch(r"[A-Za-z0-9_.\-]{2,80}", parts[0]) or first in OWN_HANDLES:
            return None
        return "facebook", first, f"https://www.facebook.com/{parts[0]}"
    if host == "tiktok.com":
        if not parts or not parts[0].startswith("@"):
            return None
        handle = parts[0][1:]
        if not re.fullmatch(r"[A-Za-z0-9_.]{2,30}", handle) or handle.lower() in _TT_RESERVED | OWN_HANDLES:
            return None
        return "tiktok", "@" + handle.lower(), f"https://www.tiktok.com/@{handle.lower()}"
    if host == "wa.me":
        num = _digits(parts[0]) if parts else ""
        return ("whatsapp", num, f"https://wa.me/{num}") if 8 <= len(num) <= 15 else None
    if host in ("api.whatsapp.com", "whatsapp.com", "wa.link"):
        if host == "wa.link":
            return None   # acortador: no se sabe el numero sin abrirlo
        num = _digits((parse_qs(parsed.query).get("phone") or [""])[0])
        return ("whatsapp", num, f"https://wa.me/{num}") if 8 <= len(num) <= 15 else None
    return None


def extract_channels(page_html: str, source_url: str) -> dict[str, dict]:
    """Canales publicados en una pagina: {red: {value, url, source}}. El primero de cada red gana
    (los enlaces <a href> van antes que URLs sueltas en el texto)."""
    out: dict[str, dict] = {}
    html_text = page_html or ""
    for url in HREF_ANY.findall(html_text) + URL_ANY.findall(html_text):
        found = classify_link(url.replace("&amp;", "&"))
        if found and found[0] not in out:
            out[found[0]] = {"value": found[1], "url": found[2], "source": source_url}
    return out


def channel_from_website(website: str) -> Optional[tuple[str, dict]]:
    """Si el "website" de Google es una red social, se guarda como esa red (fuente: Google)."""
    found = classify_link(website or "")
    if not found:
        return None
    return found[0], {"value": found[1], "url": found[2], "source": "google:website"}


def merge_channels(old: Optional[dict], new: dict) -> dict:
    out = dict(old or {})
    for k, v in (new or {}).items():
        if v and (k not in out or not out[k].get("value")):
            out[k] = v
    return out


def social_keys(channels: dict) -> list[str]:
    """Valores para la lista de exclusion de redes (red:valor)."""
    return [f"{k}:{(v or {}).get('value')}" for k, v in (channels or {}).items()
            if k in ("instagram", "facebook", "tiktok", "whatsapp") and (v or {}).get("value")]


# ---------------------------------------------------------------- vigencia
def _ts(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00")) if v else None
    except ValueError:
        return None
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def vigencia(place: dict, *, at: datetime, months: int = 12, min_reviews: int = 3,
             prev_count: Optional[int] = None, prev_at: Optional[datetime] = None,
             prev_activity: Optional[datetime] = None) -> dict:
    """{estado, motivo, last_activity_at, rating_count, has_hours} con lo que Places ya entrega.
    estado: activo | por_verificar."""
    window = timedelta(days=round(months * 30.4))
    status = str(place.get("businessStatus") or "OPERATIONAL")
    count = place.get("userRatingCount")
    count = int(count) if isinstance(count, (int, float)) else None
    has_hours = bool((place.get("regularOpeningHours") or {}).get("periods") or
                     (place.get("regularOpeningHours") or {}).get("weekdayDescriptions"))
    last = _ts(prev_activity)
    review_dates = [_ts(r.get("publishTime")) for r in (place.get("reviews") or []) if isinstance(r, dict)]
    review_dates = [d for d in review_dates if d]
    if review_dates:
        last = max([d for d in (last, max(review_dates)) if d])
    if count is not None and prev_count is not None and count > prev_count and prev_at:
        last = max([d for d in (last, at) if d])        # llegaron resenas nuevas desde el ultimo refresco
    base = {"last_activity_at": last, "rating_count": count, "has_hours": has_hours}
    if status == "CLOSED_TEMPORARILY":
        return {**base, "estado": "por_verificar", "motivo": "Google lo marca cerrado temporalmente"}
    if status not in ("OPERATIONAL", ""):
        return {**base, "estado": "por_verificar", "motivo": f"Google: {status.lower()}"}
    if last and at - last <= window:
        return {**base, "estado": "activo", "motivo": f"actividad en Google el {last.date().isoformat()}"}
    if review_dates and last and at - last > window:
        return {**base, "estado": "por_verificar", "motivo": f"última reseña hace más de {months} meses"}
    if has_hours and (count or 0) >= min_reviews:
        return {**base, "estado": "activo", "motivo": f"horario publicado y {count} reseñas en Google"}
    falta = "sin horario publicado" if not has_hours else f"solo {count or 0} reseña(s)"
    return {**base, "estado": "por_verificar", "motivo": f"sin actividad visible en {months} meses ({falta})"}


# ---------------------------------------------------------------- textos (correo y cola asistida)
LIVE3D_LINE = ("Nuevo: Negocio en vivo 3D, para ver su operación funcionando en vivo en una vista 3D, "
               "desde el celular o un televisor.")
PITCH = {
    "restaurante": ("la carta en video con QR", "sus clientes escanean el QR de la mesa, ven sus platos en video y piden desde el celular"),
    "bar": ("las fugas de dinero del bar", "pedidos por QR desde la mesa, cuenta exacta por mesa, inventario que se descuenta solo y cierre de caja por noche"),
    "taller": ("la producción por lote y la nómina", "producción por lote con el costo real de cada prenda y la nómina lista desde las horas reales"),
    "campo": ("el control del personal en campo", "turnos con GPS desde el celular o un bot, cortes por WhatsApp, órdenes de materiales y nómina por horas"),
    "transporte": ("el control de rutas y despachos", "despachos y llamadas registrados, turnos del personal y reportes en una sola herramienta"),
    "tienda": ("las ventas y el inventario de la tienda", "ventas del día, inventario que cuadra con lo vendido y turnos del equipo, desde el celular"),
}

AUDIENCE = {"restaurante": "restaurantes", "bar": "bares", "taller": "talleres y fábricas", "campo": "empresas con personal en campo",
            "transporte": "empresas de transporte", "tienda": "tiendas y minimercados"}


def assisted_text(*, name: str, niche: str, url: str, followup: bool) -> str:
    """Compatibilidad: el texto vive en app/services/prospecting_messages.py (CLONEXA, sin nombre de una persona)."""
    from app.services import prospecting_messages as pm

    return pm.followup_message(name=name, niche=niche) if followup else pm.first_message(name=name, niche=niche, link=url)


# ---------------------------------------------------------------- ruta de visitas
def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def order_route(start: tuple[float, float], stops: list[dict], limit: int = 20) -> list[dict]:
    """Vecino mas cercano desde el punto de partida: cada parada es la mas cercana a la anterior."""
    pending = [s for s in stops if s.get("lat") is not None and s.get("lng") is not None]
    out, cur, total = [], start, 0.0
    while pending and len(out) < limit:
        nxt = min(pending, key=lambda s: haversine_m(cur[0], cur[1], s["lat"], s["lng"]))
        d = haversine_m(cur[0], cur[1], nxt["lat"], nxt["lng"])
        total += d
        out.append({**nxt, "orden": len(out) + 1, "desde_anterior_m": int(round(d)), "acumulado_m": int(round(total))})
        pending.remove(nxt)
        cur = (nxt["lat"], nxt["lng"])
    return out


def maps_place_url(name: str, place_id: str = "", lat: Optional[float] = None, lng: Optional[float] = None) -> str:
    if place_id and not place_id.startswith("clonexa-"):
        return f"https://www.google.com/maps/search/?api=1&query={quote(name or '', safe='')}&query_place_id={quote(place_id, safe='')}"
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"


def maps_route_url(start: tuple[float, float], stops: list[dict]) -> str:
    """Una ruta a pie en Google Maps con las primeras 9 paradas (limite de waypoints del enlace)."""
    pts = [s for s in stops if s.get("lat") is not None][:10]
    if not pts:
        return ""
    dest = pts[-1]
    q = {"api": "1", "origin": f"{start[0]},{start[1]}", "destination": f"{dest['lat']},{dest['lng']}", "travelmode": "walking"}
    if len(pts) > 1:
        q["waypoints"] = "|".join(f"{p['lat']},{p['lng']}" for p in pts[:-1])
    return "https://www.google.com/maps/dir/?" + urlencode(q, safe="|,")


# ---------------------------------------------------------------- costos estimados (USD, lista de Google)
# https://developers.google.com/maps/billing-and-pricing/pricing : primer tramo, por 1.000 llamadas, despues del
# uso gratis mensual de cada SKU. La field mask actual (telefono y web) ya es Enterprise: horario y numero de
# resenas no suben el SKU. Las resenas (fecha de la ultima) son Enterprise + Atmosphere: apagadas.
SKU_PRICE = {
    "places_text": ("Text Search Enterprise", 35.0, 1000),
    "places_text_atmos": ("Text Search Enterprise + Atmosphere", 40.0, 1000),
    "places_details": ("Place Details Enterprise", 20.0, 1000),
    "places_details_atmos": ("Place Details Enterprise + Atmosphere", 25.0, 1000),
}


def estimate_cost(calls_by_kind: dict[str, int], month_calls_by_kind: Optional[dict[str, int]] = None) -> dict:
    """Costo de la lista (sin descontar el uso gratis) y lo que se pagaria si el mes ya paso el gratis."""
    rows, total = [], 0.0
    for kind, n in sorted(calls_by_kind.items()):
        label, price, free = SKU_PRICE.get(kind, (kind, 0.0, 0))
        cost = n * price / 1000.0
        total += cost
        month = (month_calls_by_kind or {}).get(kind, 0)
        rows.append({"sku": label, "llamadas": n, "usd_lista": round(cost, 2), "mes": month, "gratis_mes": free,
                     "sobre_gratis": max(0, month - free)})
    return {"rows": rows, "usd_lista": round(total, 2)}
