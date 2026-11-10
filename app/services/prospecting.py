"""Prospeccion por ubicacion de Nexa (interno de Clonexa: sin company_id, solo Admin V2 / v2+).

Reglas que se cumplen AQUI (no solo en n8n):
- Sin duplicados (place_id unico), sin cadenas (lista editable), solo negocios abiertos (OPERATIONAL).
- Correo solo si el negocio lo publica en su web (pagina principal o de contacto); se guarda la URL de
  donde salio. Nada de correos adivinados ni personales (ver business_email_ok).
- Ley 2300 de 2023 (como la pidio el dueno): contacto solo lunes a viernes 8:00-17:00 hora Bogota (y
  no en festivos), maximo 1 contacto por semana por negocio, 1 correo + 1 seguimiento a los 7 dias y
  nada mas. Baja inmediata y permanente (prospect_exclusions); quien responde NO queda de baja.
- Ningun correo sale sin un lote APROBADO por el dueno (Telegram) para ese dia.
- Google Places: se guarda place_id y lo demas se refresca cada 30 dias (refresh_due).
- WhatsApp: nunca en frio; solo se liga cuando el negocio escribe primero con su codigo.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import ipaddress
import json
import logging
import math
import re
import secrets
import socket
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import prospecting_email as pe
from app.services.payroll_colombia import colombian_holidays

log = logging.getLogger("clonexa.prospecting")

BOGOTA = timezone(timedelta(hours=-5))
TYPES = ("restaurante", "comidas_rapidas", "cafe", "panaderia", "bar", "taller")
TYPE_LABEL = {"restaurante": "Restaurante", "comidas_rapidas": "Comidas rápidas", "cafe": "Café",
              "panaderia": "Panadería", "bar": "Bar", "taller": "Taller de confección"}
STATUSES = ("nuevo", "contactado", "abrio", "respondio", "demo", "cliente", "baja")
STATUS_LABEL = {"nuevo": "Nuevo", "contactado": "Contactado", "abrio": "Abrió la landing", "respondio": "Respondió",
                "demo": "Demo", "cliente": "Cliente", "baja": "Baja"}
RANK = {s: i for i, s in enumerate(STATUSES)}
SEARCH = {
    "restaurante": ("restaurantes", "restaurant"),
    "comidas_rapidas": ("comidas rápidas", "fast_food_restaurant"),
    "cafe": ("cafeterías", "cafe"),
    "panaderia": ("panaderías", "bakery"),
    "bar": ("bares", "bar"),
    "taller": ("taller de confección", None),
}
FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.addressComponents", "places.location",
    "places.types", "places.primaryType", "places.businessStatus", "places.nationalPhoneNumber", "places.websiteUri",
    "nextPageToken",
])
DETAIL_FIELD_MASK = ("id,displayName,formattedAddress,addressComponents,location,types,primaryType,businessStatus,"
                     "nationalPhoneNumber,websiteUri")
RESCAN_DAYS = 6
REFRESH_DAYS = 30
FOLLOWUP_DAYS = 7
WEEK_DAYS = 7
MAX_EMAILS = 2  # 1 correo + 1 seguimiento
STALE_CLAIM_MIN = 30
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
DEFAULT_SETTINGS = {
    "daily_limit": 25,
    "min_gap_minutes": 9,
    "window_start": 8,
    "window_end": 17,
    "signature": "Nicolás Gómez · Clonexa",
    "sender_name": "Clonexa",
    "sender_email": "",  # vacio = la cuenta de Gmail conectada en n8n
    "reply_to": "",
    "test_recipient": "",  # vacio = el correo de Admin V2
    "landing_url": pe.DEFAULT_LANDING,
    "backend_url": pe.DEFAULT_BACKEND,
    "wa_number": pe.WA_NUMBER,
}


# ---------------------------------------------------------------- utilidades puras
def now() -> datetime:
    return datetime.now(timezone.utc)


def fold(value: Any) -> str:
    raw = unicodedata.normalize("NFD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", raw).split())


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


def _chain_words(value: str) -> list[str]:
    return [w for w in fold(str(value or "").replace("&", " ")).split() if w not in ("and", "y", "the")]


def is_chain(name: str, chains: Iterable[str]) -> bool:
    """Cadena si su nombre aparece como palabras completas ("Frisby Americas"); para nombres de varias
    palabras tambien sin espacios ("McDonalds" = "McDonald's"). "Prestofino" no es "Presto"."""
    words = _chain_words(name)
    if not words:
        return False
    padded = f" {' '.join(words)} "
    flat_words = set(words) | {"".join(words[i:i + n]) for n in (2, 3) for i in range(len(words) - n + 1)}
    for c in chains:
        cw = _chain_words(c)
        if not cw:
            continue
        if f" {' '.join(cw)} " in padded:
            return True
        if len(cw) >= 2 and "".join(cw) in flat_words:
            return True
    return False


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def point_in_polygon(lat: float, lng: float, polygon: list) -> bool:
    inside = False
    pts = [(float(p[0]), float(p[1])) for p in polygon or [] if isinstance(p, (list, tuple)) and len(p) >= 2]
    j = len(pts) - 1
    for i in range(len(pts)):
        yi, xi = pts[i]
        yj, xj = pts[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def in_zone(zone: dict, lat: Optional[float], lng: Optional[float], slack: float = 1.25) -> bool:
    if lat is None or lng is None:
        return False
    if zone.get("kind") == "polygon" and zone.get("polygon"):
        return point_in_polygon(lat, lng, zone["polygon"])
    return haversine_m(zone["center_lat"], zone["center_lng"], lat, lng) <= float(zone["radius_m"]) * slack


def classify_type(place: dict, searched: str) -> str:
    if searched == "taller":
        return "taller"
    primary = str(place.get("primaryType") or "")
    types = set(place.get("types") or [])
    if primary in ("bar", "pub", "wine_bar", "night_club") or (searched == "bar" and "bar" in types):
        return "bar"
    if primary in ("bakery",):
        return "panaderia"
    if primary in ("cafe", "coffee_shop", "cafeteria", "tea_house"):
        return "cafe"
    if primary in ("fast_food_restaurant", "hamburger_restaurant", "sandwich_shop", "pizza_restaurant", "hot_dog_restaurant"):
        return "comidas_rapidas"
    if primary.endswith("_restaurant") or primary == "restaurant":
        return "restaurante"
    return searched


SOCIAL_HOSTS = ("instagram.com", "facebook.com", "fb.com", "fb.me", "wa.me", "whatsapp.com", "api.whatsapp.com",
                "linktr.ee", "tiktok.com", "twitter.com", "x.com", "youtube.com", "youtu.be", "rappi.com", "rappi.com.co",
                "ifood.com.co", "domicilios.com", "google.com", "goo.gl", "g.page", "business.site", "beacons.ai",
                "linkin.bio", "ubereats.com", "didi-food.com", "tripadvisor.com", "tripadvisor.co", "maps.app.goo.gl",
                "bit.ly", "taplink.cc", "wix.to", "msha.ke", "carta.menu", "menu.app")
FREE_MAIL = {"gmail.com", "hotmail.com", "hotmail.es", "outlook.com", "outlook.es", "yahoo.com", "yahoo.es",
             "yahoo.com.co", "live.com", "msn.com", "icloud.com", "me.com", "aol.com", "protonmail.com", "proton.me"}
GENERIC_LOCAL = {"info", "informacion", "contacto", "contact", "contactenos", "hola", "hello", "reservas", "reserva",
                 "ventas", "venta", "pedidos", "pedido", "domicilios", "domicilio", "servicio", "servicioalcliente",
                 "cliente", "clientes", "admin", "administracion", "gerencia", "eventos", "comercial", "atencion",
                 "atencionalcliente", "office", "oficina", "recepcion", "compras", "facturacion", "mercadeo", "marketing"}
NAME_STOPWORDS = {"restaurante", "restaurant", "bar", "cafe", "cafeteria", "panaderia", "pasteleria", "comidas", "rapidas",
                  "taller", "confeccion", "confecciones", "bogota", "kennedy", "the", "los", "las", "del", "con", "san",
                  "sas", "ltda", "grill", "parrilla", "asadero", "pizzeria", "comida", "casa", "food", "express"}
BAD_EMAIL_HOST = ("example.com", "example.org", "sentry.io", "sentry-next.wixpress.com", "wixpress.com", "wix.com",
                  "godaddy.com", "squarespace.com", "wordpress.com", "mailchimp.com", "domain.com", "email.com",
                  "tudominio.com", "sudominio.com", "dominio.com", "correo.com", "yourdomain.com", "company.com")
EMAIL_RE = re.compile(r"(?<![\w.+-])([a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24})(?![\w-])", re.I)
CONTACT_HINT = re.compile(r"contact|cont[aá]ct|escr[ií]benos|ubicaci[oó]n|nosotros", re.I)
HREF_RE = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def host_of(url: str) -> str:
    try:
        h = (urlparse(url if "://" in url else "http://" + url).hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def registrable(host: str) -> str:
    parts = [p for p in (host or "").lower().split(".") if p]
    if len(parts) >= 3 and parts[-2] in ("com", "net", "org", "gov", "edu", "co") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_social(url: str) -> bool:
    h = host_of(url)
    return any(h == s or h.endswith("." + s) for s in SOCIAL_HOSTS)


def business_email_ok(email: str, website: str, business_name: str) -> tuple[bool, str]:
    """Solo correos del negocio: dominio de su web, buzon generico (info@, contacto@...) o, si es de un
    proveedor gratis, que el buzon lleve el nombre del negocio. Lo demas puede ser personal: no."""
    e = (email or "").strip().lower()
    if "@" not in e:
        return False, "invalido"
    local, domain = e.rsplit("@", 1)
    if any(domain == b or domain.endswith("." + b) for b in BAD_EMAIL_HOST) or re.search(r"\.(png|jpe?g|gif|webp|svg)$", e):
        return False, "invalido"
    if re.search(r"no-?reply|donotreply|mailer|postmaster|bounce", local):
        return False, "automatico"
    site = registrable(host_of(website)) if website else ""
    if site and registrable(domain) == site:
        return True, "dominio_propio"
    flat_local = re.sub(r"[^a-z]", "", local)
    if flat_local in GENERIC_LOCAL or any(flat_local.startswith(g) and len(flat_local) - len(g) <= 3 for g in GENERIC_LOCAL if len(g) >= 5):
        return (True, "generico") if domain in FREE_MAIL or not site else (False, "otro_dominio")
    if domain in FREE_MAIL:
        words = [w for w in fold(business_name).split() if len(w) >= 4 and w not in NAME_STOPWORDS]
        if any(w in flat_local for w in words):
            return True, "nombre_del_negocio"
        return False, "posible_personal"
    return False, "otro_dominio"


def extract_emails(page_html: str) -> list[str]:
    raw = html_lib.unescape(page_html or "")
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.I | re.S) + " " + " ".join(
        re.findall(r"mailto:([^\"'?>\s]+)", html_lib.unescape(page_html or ""), flags=re.I))
    seen, out = set(), []
    for m in EMAIL_RE.findall(raw):
        e = m.strip(".").lower()
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def best_email(page_html: str, website: str, business_name: str) -> Optional[tuple[str, str]]:
    ranked = []
    order = {"dominio_propio": 0, "generico": 1, "nombre_del_negocio": 2}
    for e in extract_emails(page_html):
        ok, why = business_email_ok(e, website, business_name)
        if ok:
            ranked.append((order[why], e, why))
    if not ranked:
        return None
    ranked.sort()
    return ranked[0][1], ranked[0][2]


def contact_link(page_html: str, base_url: str) -> str:
    base_host = host_of(base_url)
    for href, label in HREF_RE.findall(page_html or ""):
        if CONTACT_HINT.search(href) or CONTACT_HINT.search(re.sub(r"<[^>]+>", " ", label)):
            url = urljoin(base_url, href.strip())
            if url.startswith(("http://", "https://")) and host_of(url) == base_host:
                return url
    return ""


def bogota(at: Optional[datetime] = None) -> datetime:
    return (at or now()).astimezone(BOGOTA)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in colombian_holidays(d.year)


def in_legal_window(at: Optional[datetime] = None, start: int = 8, end: int = 17) -> bool:
    b = bogota(at)
    return is_business_day(b.date()) and start <= b.hour < end


NEGATIVE = re.compile(
    r"\b(no me interesa|no nos interesa|no estoy interesad|no estamos interesad|no gracias|no, gracias|no quiero|"
    r"no queremos|no deseo|no deseamos|no me escriban|no nos escriban|no vuelvan|no env[ií]en|dejen de|"
    r"dar(me|nos)? de baja|darme de baja|de baja|quitar(me|nos)? de|qu[ií]ten(me|nos)|retir(en|ar)(me|nos)?|"
    r"eliminar mi correo|eliminen|unsubscribe|remove me|stop)\b", re.I)


def strip_quoted(body: str) -> str:
    lines = []
    for line in (body or "").splitlines():
        s = line.strip()
        if s.startswith(">") or re.match(r"^(el|on)\s.+(escribi[oó]|wrote):?$", s, re.I) or s.startswith("-----"):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def is_negative(body: str, subject: str = "") -> bool:
    fresh = strip_quoted(body)
    words = fold(fresh).split()
    if words and words[0] == "no" and len(words) <= 6:
        return True
    return bool(NEGATIVE.search(fresh)) or bool(NEGATIVE.search(re.sub(r"^\s*(re|rv|fw|fwd)\s*:\s*", "", subject or "", flags=re.I)))


CODE_RE = re.compile(r"c[oó]digo\s*[:#]?\s*([A-Za-z0-9]{6})\b", re.I)


def code_in(text_: str) -> str:
    m = CODE_RE.search(text_ or "")
    return m.group(1).upper() if m else ""


def mask_email(email: str) -> str:
    e = (email or "").strip()
    if "@" not in e:
        return ""
    local, domain = e.split("@", 1)
    return (local[:1] + "•••" if local else "•••") + "@" + domain


# ---------------------------------------------------------------- web del negocio (sin SSRF)
USER_AGENT = "Mozilla/5.0 (compatible; ClonexaBot/1.0; +https://www.clonexa.com.co)"
MAX_PAGE = 1_500_000


def _public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return bool(infos)


async def fetch_page(url: str, *, client: Optional[httpx.AsyncClient] = None, timeout: float = 8.0) -> tuple[str, str]:
    """(url_final, html) o ("", ""). Solo http(s) a IPs publicas, max 3 redirecciones, max 1,5 MB."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers={"User-Agent": USER_AGENT})
    try:
        current = url if "://" in url else "http://" + url
        for _ in range(4):
            parsed = urlparse(current)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return "", ""
            if not await asyncio.to_thread(_public_host, parsed.hostname):
                return "", ""
            async with client.stream("GET", current) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    current = urljoin(current, r.headers["location"])
                    continue
                if r.status_code != 200 or "html" not in (r.headers.get("content-type") or "text/html").lower():
                    return "", ""
                chunks, size = [], 0
                async for chunk in r.aiter_bytes():
                    size += len(chunk)
                    chunks.append(chunk)
                    if size > MAX_PAGE:
                        break
                return current, b"".join(chunks).decode(r.encoding or "utf-8", errors="replace")
        return "", ""
    except (httpx.HTTPError, ValueError, UnicodeError):
        return "", ""
    finally:
        if own:
            await client.aclose()


async def scan_website(website: str, name: str, fetch=None) -> dict:
    """Pagina principal y, si no hay correo, la de contacto. {email, why, source_url, status}."""
    fetch = fetch or fetch_page
    if not website:
        return {"email": "", "why": "", "source_url": "", "status": "sin_web"}
    if is_social(website):
        return {"email": "", "why": "", "source_url": "", "status": "sin_web"}
    final, page = await fetch(website)
    if not page:
        return {"email": "", "why": "", "source_url": "", "status": "web_caida"}
    found = best_email(page, final or website, name)
    if found:
        return {"email": found[0], "why": found[1], "source_url": final or website, "status": "encontrado"}
    link = contact_link(page, final or website)
    if link:
        f2, p2 = await fetch(link)
        found = best_email(p2, f2 or website, name) if p2 else None
        if found:
            return {"email": found[0], "why": found[1], "source_url": f2 or link, "status": "encontrado"}
    return {"email": "", "why": "", "source_url": "", "status": "sin_correo"}


# ---------------------------------------------------------------- base
async def _rows(db: AsyncSession, sql: str, params: Optional[dict] = None) -> list[dict]:
    return [dict(r) for r in (await db.execute(text(sql), params or {})).mappings().all()]


async def _one(db: AsyncSession, sql: str, params: Optional[dict] = None) -> Optional[dict]:
    r = (await db.execute(text(sql), params or {})).mappings().first()
    return dict(r) if r else None


async def get_settings(db: AsyncSession) -> dict:
    row = await _one(db, "SELECT config FROM prospect_settings WHERE id = 1")
    cfg = dict(DEFAULT_SETTINGS)
    cfg.update({k: v for k, v in ((row or {}).get("config") or {}).items() if k in DEFAULT_SETTINGS})
    return cfg


async def save_settings(db: AsyncSession, changes: dict) -> dict:
    cfg = await get_settings(db)
    for k, v in changes.items():
        if k in DEFAULT_SETTINGS and v is not None:
            cfg[k] = v
    cfg["daily_limit"] = max(1, min(25, int(cfg["daily_limit"])))  # nunca mas de 25 al dia
    cfg["window_start"] = max(8, min(16, int(cfg["window_start"])))
    cfg["window_end"] = max(cfg["window_start"] + 1, min(17, int(cfg["window_end"])))
    cfg["min_gap_minutes"] = max(3, min(60, int(cfg["min_gap_minutes"])))
    await db.execute(text("""INSERT INTO prospect_settings (id, config, updated_at) VALUES (1, CAST(:c AS jsonb), now())
                             ON CONFLICT (id) DO UPDATE SET config = EXCLUDED.config, updated_at = now()"""),
                     {"c": json.dumps(cfg)})
    await db.commit()
    return cfg


async def chains(db: AsyncSession, active_only: bool = True) -> list[dict]:
    return await _rows(db, "SELECT id, name, active FROM prospect_chains" + (" WHERE active" if active_only else "") + " ORDER BY name")


async def set_chains(db: AsyncSession, names: list[str]) -> list[dict]:
    clean = sorted({" ".join(str(n).split())[:120] for n in names if str(n).strip()})
    await db.execute(text("UPDATE prospect_chains SET active = false WHERE NOT (name = ANY(CAST(:n AS text[])))"), {"n": clean})
    for n in clean:
        await db.execute(text("INSERT INTO prospect_chains (name) VALUES (:n) ON CONFLICT (name) DO UPDATE SET active = true"), {"n": n})
    await db.commit()
    return await chains(db)


ZONE_COLS = "id, slug, name, group_name, city, kind, center_lat, center_lng, radius_m, polygon, active, sort"


async def zones(db: AsyncSession, active_only: bool = False) -> list[dict]:
    return await _rows(db, f"SELECT {ZONE_COLS} FROM prospect_zones" + (" WHERE active" if active_only else "") + " ORDER BY sort, id")


def slugify(value: str) -> str:
    return "-".join(fold(value).split())[:60] or "zona"


async def save_zone(db: AsyncSession, data: dict, zone_id: Optional[int] = None) -> dict:
    params = {
        "name": " ".join(str(data["name"]).split())[:120],
        "group_name": " ".join(str(data.get("group_name") or "").split())[:120],
        "city": " ".join(str(data.get("city") or "Bogotá").split())[:80],
        "kind": "polygon" if data.get("polygon") else "circle",
        "lat": float(data["center_lat"]), "lng": float(data["center_lng"]),
        "radius": int(data.get("radius_m") or 700),
        "polygon": json.dumps(data["polygon"]) if data.get("polygon") else None,
        "active": bool(data.get("active", True)),
    }
    if zone_id is None:
        params["slug"] = slugify(data.get("slug") or data["name"])
        row = await _one(db, f"""
            INSERT INTO prospect_zones (slug, name, group_name, city, kind, center_lat, center_lng, radius_m, polygon, active, sort)
            VALUES (:slug, :name, :group_name, :city, :kind, :lat, :lng, :radius, CAST(:polygon AS jsonb), :active,
                    COALESCE((SELECT MAX(sort) + 1 FROM prospect_zones), 0))
            ON CONFLICT (slug) DO NOTHING RETURNING {ZONE_COLS}""", params)
        if not row:
            raise ValueError("zona_repetida")
    else:
        params["id"] = zone_id
        row = await _one(db, f"""
            UPDATE prospect_zones SET name = :name, group_name = :group_name, city = :city, kind = :kind,
                center_lat = :lat, center_lng = :lng, radius_m = :radius, polygon = CAST(:polygon AS jsonb),
                active = :active, updated_at = now()
            WHERE id = :id RETURNING {ZONE_COLS}""", params)
        if not row:
            raise LookupError("zona_no_existe")
    await db.commit()
    return row


# ---------------------------------------------------------------- busqueda en Google Places
def places_request(zone: dict, business_type: str, page_token: str = "") -> dict:
    query, included = SEARCH[business_type]
    body: dict[str, Any] = {
        "textQuery": f"{query} en {zone['name']}, {zone.get('city') or 'Bogotá'}",
        "languageCode": "es", "regionCode": "CO", "pageSize": 20,
        "locationBias": {"circle": {"center": {"latitude": zone["center_lat"], "longitude": zone["center_lng"]},
                                    "radius": float(min(50000, max(200, zone["radius_m"])))}},
    }
    if included:
        body["includedType"] = included
    if page_token:
        body["pageToken"] = page_token
    return {"url": "https://places.googleapis.com/v1/places:searchText", "field_mask": FIELD_MASK, "body": body}


async def scan_plan(db: AsyncSession, *, max_searches: int = 12, zone_slug: str = "", types: Optional[list[str]] = None,
                    force: bool = False) -> list[dict]:
    zs = [z for z in await zones(db, active_only=True) if not zone_slug or z["slug"] == zone_slug or slugify(z["group_name"]) == zone_slug]
    wanted = [t for t in (types or TYPES) if t in TYPES]
    state = {(r["zone_id"], r["business_type"]): r for r in await _rows(db, "SELECT * FROM prospect_zone_scans")}
    cut = now() - timedelta(days=RESCAN_DAYS)
    plan = []
    for z in zs:
        for t in wanted:
            st = state.get((z["id"], t)) or {}
            token = st.get("next_page_token") or ""
            last = st.get("last_scanned_at")
            if not force and last and last > cut and not token:
                continue
            plan.append((last or datetime.min.replace(tzinfo=timezone.utc), z, t, token))
    plan.sort(key=lambda p: (p[0], p[1]["sort"]))
    return [{"zone_id": z["id"], "zone": z["slug"], "zone_name": z["name"], "business_type": t,
             "request": places_request(z, t, token)} for _, z, t, token in plan[:max(1, min(40, max_searches))]]


def _component(place: dict, *kinds: str) -> str:
    for c in place.get("addressComponents") or []:
        if set(c.get("types") or []) & set(kinds):
            return str(c.get("longText") or c.get("shortText") or "")[:120]
    return ""


async def _excluded(db: AsyncSession, *, email: str = "", place_id: str = "") -> bool:
    e = (email or "").strip().lower()
    d = e.rsplit("@", 1)[1] if "@" in e else ""
    row = await _one(db, """SELECT 1 AS x FROM prospect_exclusions WHERE (kind = 'email' AND value = :e AND :e <> '')
                            OR (kind = 'domain' AND value = :d AND :d <> '') OR (kind = 'place' AND value = :p AND :p <> '') LIMIT 1""",
                     {"e": e, "d": d, "p": place_id or ""})
    return bool(row)


async def _unique_code(db: AsyncSession) -> str:
    for _ in range(20):
        c = new_code()
        if not await _one(db, "SELECT 1 AS x FROM prospects WHERE code = :c", {"c": c}):
            return c
    raise RuntimeError("no_code")


async def ingest_places(db: AsyncSession, *, zone_id: int, business_type: str, places: list[dict], next_page_token: str = "",
                        limit_new: Optional[int] = None, scan_web: bool = True, fetch=None) -> dict:
    zone = await _one(db, f"SELECT {ZONE_COLS} FROM prospect_zones WHERE id = :i", {"i": zone_id})
    if not zone:
        raise LookupError("zona_no_existe")
    if business_type not in TYPES:
        raise ValueError("tipo_invalido")
    chain_names = [c["name"] for c in await chains(db)]
    out = {"found": len(places), "new": 0, "duplicate": 0, "chain": 0, "closed": 0, "outside": 0, "excluded": 0,
           "with_email": 0, "new_ids": []}
    new_rows = []
    for p in places:
        if limit_new is not None and out["new"] >= limit_new:
            break
        pid = str(p.get("id") or "").strip()
        name = str((p.get("displayName") or {}).get("text") or "").strip()
        if not pid or not name:
            continue
        status = str(p.get("businessStatus") or "OPERATIONAL")
        if status != "OPERATIONAL":
            out["closed"] += 1
            continue
        if is_chain(name, chain_names):
            out["chain"] += 1
            continue
        loc = p.get("location") or {}
        lat, lng = loc.get("latitude"), loc.get("longitude")
        if not in_zone(zone, lat, lng):
            out["outside"] += 1
            continue
        if await _excluded(db, place_id=pid):
            out["excluded"] += 1
            continue
        if await _one(db, "SELECT 1 AS x FROM prospects WHERE place_id = :p", {"p": pid}):
            out["duplicate"] += 1
            continue
        btype = classify_type(p, business_type)
        website = str(p.get("websiteUri") or "")[:500]
        row = await _one(db, """
            INSERT INTO prospects (place_id, code, unsub_token, name, business_type, primary_type, google_types, address,
                                   locality, neighborhood, zone_id, lat, lng, phone, website, business_status, email_status)
            VALUES (:pid, :code, :tok, :name, :btype, :ptype, CAST(:types AS jsonb), :addr, :loc, :nb, :zone, :lat, :lng,
                    :phone, :web, :bs, :es)
            ON CONFLICT (place_id) DO NOTHING RETURNING id::text AS id""", {
            "pid": pid[:300], "code": await _unique_code(db), "tok": secrets.token_urlsafe(24), "name": name[:200],
            "btype": btype, "ptype": str(p.get("primaryType") or "")[:80], "types": json.dumps((p.get("types") or [])[:20]),
            "addr": str(p.get("formattedAddress") or "")[:300],
            "loc": _component(p, "sublocality_level_1", "sublocality", "administrative_area_level_3") or zone.get("group_name") or "",
            "nb": _component(p, "neighborhood") or zone["name"], "zone": zone_id, "lat": lat, "lng": lng,
            "phone": str(p.get("nationalPhoneNumber") or "")[:60], "web": website, "bs": status[:40],
            "es": "pendiente" if website and not is_social(website) else "sin_web"})
        if row:
            out["new"] += 1
            out["new_ids"].append(row["id"])
            new_rows.append({"id": row["id"], "website": website, "name": name})
        else:
            out["duplicate"] += 1
    await db.execute(text("""
        INSERT INTO prospect_zone_scans (zone_id, business_type, last_scanned_at, next_page_token, pages, last_found, last_new)
        VALUES (:z, :t, now(), :tok, 1, :f, :n)
        ON CONFLICT (zone_id, business_type) DO UPDATE SET last_scanned_at = now(), next_page_token = EXCLUDED.next_page_token,
            pages = CASE WHEN EXCLUDED.next_page_token = '' THEN 0 ELSE prospect_zone_scans.pages + 1 END,
            last_found = EXCLUDED.last_found, last_new = EXCLUDED.last_new"""),
                     {"z": zone_id, "t": business_type, "tok": (next_page_token or "")[:2000], "f": len(places), "n": out["new"]})
    await db.commit()
    if scan_web:
        targets = [r for r in new_rows if r["website"] and not is_social(r["website"])]
        out["with_email"] = await scan_many(db, targets, fetch=fetch)
    return out


async def scan_many(db: AsyncSession, targets: list[dict], *, fetch=None, concurrency: int = 5) -> int:
    sem = asyncio.Semaphore(concurrency)

    async def one(t):
        async with sem:
            try:
                return t, await asyncio.wait_for(scan_website(t["website"], t["name"], fetch=fetch), 25)
            except Exception:  # noqa: BLE001 - una web mala no tumba el lote
                return t, {"email": "", "why": "", "source_url": "", "status": "web_caida"}

    found = 0
    for t, res in await asyncio.gather(*(one(t) for t in targets)):
        found += await save_email_scan(db, t["id"], res)
    await db.commit()
    return found


async def save_email_scan(db: AsyncSession, prospect_id: str, res: dict) -> int:
    email, status = res.get("email") or "", res.get("status") or "sin_correo"
    if email and await _excluded(db, email=email):
        email, status = "", "excluido"
    if email:
        dup = await _one(db, "SELECT 1 AS x FROM prospects WHERE lower(email) = :e AND id <> CAST(:i AS uuid)", {"e": email, "i": prospect_id})
        if dup:  # la misma cadena/duenio con varias sedes: un solo contacto por correo
            email, status = "", "correo_repetido"
    await db.execute(text("""UPDATE prospects SET email = :e, email_source_url = :s, email_status = :st, email_checked_at = now(),
                             updated_at = now() WHERE id = CAST(:i AS uuid)"""),
                     {"e": email[:200], "s": (res.get("source_url") or "")[:500] if email else "", "st": status, "i": prospect_id})
    return 1 if email else 0


async def scan_report(db: AsyncSession, since: datetime) -> dict:
    rows = await _rows(db, """
        SELECT z.name AS zona, z.group_name AS grupo, COUNT(p.id)::int AS nuevos,
               COUNT(p.id) FILTER (WHERE p.email <> '')::int AS con_correo
        FROM prospect_zones z LEFT JOIN prospects p ON p.zone_id = z.id AND p.created_at >= :s AND NOT p.is_test
        WHERE z.active GROUP BY z.id, z.name, z.group_name, z.sort ORDER BY z.sort""", {"s": since})
    total = await _one(db, """SELECT COUNT(*)::int AS prospectos, COUNT(*) FILTER (WHERE email <> '')::int AS con_correo
                              FROM prospects WHERE NOT is_test AND status <> 'baja'""") or {}
    return {"zonas": rows, "nuevos": sum(r["nuevos"] for r in rows), "nuevos_con_correo": sum(r["con_correo"] for r in rows),
            "total": total.get("prospectos", 0), "total_con_correo": total.get("con_correo", 0)}


async def refresh_due(db: AsyncSession, limit: int = 40) -> list[dict]:
    return await _rows(db, """SELECT id::text AS id, place_id FROM prospects
                              WHERE NOT is_test AND place_refreshed_at < now() - make_interval(days => :d)
                              ORDER BY place_refreshed_at LIMIT :l""", {"d": REFRESH_DAYS, "l": max(1, min(200, limit))})


async def apply_refresh(db: AsyncSession, prospect_id: str, place: Optional[dict], not_found: bool = False) -> dict:
    if not_found or not place:
        await db.execute(text("""UPDATE prospects SET business_status = 'NOT_FOUND', place_refreshed_at = now(), updated_at = now()
                                 WHERE id = CAST(:i AS uuid)"""), {"i": prospect_id})
        await db.commit()
        return {"ok": True, "estado": "no_encontrado"}
    loc = place.get("location") or {}
    await db.execute(text("""
        UPDATE prospects SET name = COALESCE(NULLIF(:n, ''), name), address = COALESCE(NULLIF(:a, ''), address),
            phone = :ph, website = :w, lat = COALESCE(:lat, lat), lng = COALESCE(:lng, lng),
            business_status = :bs, google_types = CAST(:t AS jsonb), place_refreshed_at = now(), updated_at = now()
        WHERE id = CAST(:i AS uuid)"""), {
        "n": str((place.get("displayName") or {}).get("text") or "")[:200], "a": str(place.get("formattedAddress") or "")[:300],
        "ph": str(place.get("nationalPhoneNumber") or "")[:60], "w": str(place.get("websiteUri") or "")[:500],
        "lat": loc.get("latitude"), "lng": loc.get("longitude"), "bs": str(place.get("businessStatus") or "OPERATIONAL")[:40],
        "t": json.dumps((place.get("types") or [])[:20]), "i": prospect_id})
    await db.commit()
    return {"ok": True, "estado": str(place.get("businessStatus") or "OPERATIONAL")}


# ---------------------------------------------------------------- contactos y estados
async def log_contact(db: AsyncSession, prospect_id: str, channel: str, kind: str, *, status: str = "registrado",
                      detail: Optional[dict] = None, **cols) -> int:
    row = await _one(db, """
        INSERT INTO prospect_contacts (prospect_id, channel, kind, status, batch_id, to_email, subject, gmail_message_id,
                                       gmail_thread_id, sent_at, detail)
        VALUES (CAST(:p AS uuid), :ch, :k, :st, :b, :to, :sub, :mid, :tid, :sent, CAST(:d AS jsonb)) RETURNING id""", {
        "p": prospect_id, "ch": channel, "k": kind, "st": status, "b": cols.get("batch_id"), "to": cols.get("to_email", ""),
        "sub": cols.get("subject", "")[:300], "mid": cols.get("gmail_message_id", ""), "tid": cols.get("gmail_thread_id", ""),
        "sent": cols.get("sent_at"), "d": json.dumps(detail or {}, ensure_ascii=False)})
    return int(row["id"])


async def _promote(db: AsyncSession, prospect_id: str, status: str, stamp_col: Optional[str] = None) -> None:
    """Sube el estado (nunca lo baja; baja siempre gana y no se revierte desde aqui)."""
    stamp = f", {stamp_col} = COALESCE({stamp_col}, now())" if stamp_col else ""
    await db.execute(text(f"""
        UPDATE prospects SET status = CASE WHEN status = 'baja' THEN status
                                           WHEN :s = 'baja' THEN 'baja'
                                           WHEN array_position(CAST(:order AS text[]), status) < array_position(CAST(:order AS text[]), :s) THEN :s
                                           ELSE status END{stamp}, updated_at = now()
        WHERE id = CAST(:i AS uuid)"""), {"s": status, "i": prospect_id, "order": list(STATUSES)})


async def unsubscribe(db: AsyncSession, prospect: dict, *, reason: str, channel: str = "email", detail: Optional[dict] = None) -> bool:
    already = prospect.get("status") == "baja"
    await db.execute(text("""UPDATE prospects SET status = 'baja', unsubscribed_at = COALESCE(unsubscribed_at, now()), updated_at = now()
                             WHERE id = CAST(:i AS uuid)"""), {"i": prospect["id"]})
    for kind, value in (("email", (prospect.get("email") or "").lower()), ("place", prospect.get("place_id") or "")):
        if value:
            await db.execute(text("INSERT INTO prospect_exclusions (kind, value, reason) VALUES (:k, :v, :r) ON CONFLICT DO NOTHING"),
                             {"k": kind, "v": value[:300], "r": reason[:40]})
    # todo lo que estaba en cola para este negocio se cancela
    await db.execute(text("""UPDATE prospect_contacts SET status = 'cancelado' WHERE prospect_id = CAST(:i AS uuid)
                             AND status IN ('pendiente', 'aprobado')"""), {"i": prospect["id"]})
    if not already:
        await log_contact(db, prospect["id"], channel, "baja", detail={"motivo": reason, **(detail or {})})
    await db.commit()
    return not already


PROSPECT_COLS = """p.id::text AS id, p.place_id, p.code, p.unsub_token, p.name, p.business_type, p.address, p.locality,
    p.neighborhood, p.zone_id, z.slug AS zone_slug, z.name AS zone_name, z.group_name AS zone_group, p.lat, p.lng, p.phone,
    p.website, p.email, p.email_source_url, p.email_status, p.status, p.is_test, p.contact_count, p.first_contacted_at,
    p.last_contacted_at, p.followup_sent_at, p.opened_at, p.replied_at, p.demo_at, p.client_at, p.unsubscribed_at,
    p.wa_consent_at, p.wa_consent_source, p.business_status, p.created_at, p.place_refreshed_at"""


async def prospect_by(db: AsyncSession, column: str, value: Any) -> Optional[dict]:
    assert column in ("id", "code", "unsub_token", "email")
    where = {"id": "p.id = CAST(:v AS uuid)", "code": "p.code = :v", "unsub_token": "p.unsub_token = :v",
             "email": "lower(p.email) = lower(:v) AND p.email <> ''"}[column]
    return await _one(db, f"SELECT {PROSPECT_COLS} FROM prospects p LEFT JOIN prospect_zones z ON z.id = p.zone_id WHERE {where} LIMIT 1",
                      {"v": value})


async def unsubscribe_by_token(db: AsyncSession, token: str, source: str = "enlace") -> tuple[Optional[dict], bool]:
    tok = (token or "").strip()
    if not tok or len(tok) > 64:
        return None, False
    p = await prospect_by(db, "unsub_token", tok)
    if not p:
        return None, False
    changed = await unsubscribe(db, p, reason="baja", detail={"origen": source})
    return p, changed


async def mark_opened(db: AsyncSession, code: str, *, medium: str = "", campaign: str = "") -> Optional[dict]:
    c = (code or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{6}", c) or (medium and medium.lower() != "prospeccion"):
        return None
    p = await prospect_by(db, "code", c)
    if not p:
        return None
    first = p["opened_at"] is None
    await _promote(db, p["id"], "abrio", "opened_at")
    seen_today = await _one(db, """SELECT 1 AS x FROM prospect_contacts WHERE prospect_id = CAST(:i AS uuid) AND kind = 'apertura'
                                   AND created_at >= now() - interval '12 hours'""", {"i": p["id"]})
    if not seen_today:
        await log_contact(db, p["id"], "landing", "apertura", detail={"campana": campaign[:120], "primera": first})
    await db.commit()
    return p


async def link_whatsapp(db: AsyncSession, message_text: str, wa_contact_id: str = "") -> Optional[dict]:
    """El negocio escribio PRIMERO con su codigo: se liga, se registra el consentimiento y queda 'respondio'."""
    c = code_in(message_text)
    if not c:
        return None
    p = await prospect_by(db, "code", c)
    if not p:
        return None
    first = p["wa_consent_at"] is None
    await db.execute(text("""UPDATE prospects SET wa_consent_at = COALESCE(wa_consent_at, now()),
                             wa_consent_source = CASE WHEN wa_consent_source = '' THEN 'escribio_con_codigo' ELSE wa_consent_source END,
                             wa_contact_id = CASE WHEN :w <> '' THEN :w ELSE wa_contact_id END, updated_at = now()
                             WHERE id = CAST(:i AS uuid)"""), {"i": p["id"], "w": (wa_contact_id or "")[:64]})
    if p["status"] != "baja":
        await _promote(db, p["id"], "respondio", "replied_at")
    await log_contact(db, p["id"], "whatsapp", "whatsapp_entrada", detail={"primera_vez": first, "texto": (message_text or "")[:300]})
    await db.commit()
    return {**p, "primera_vez": first}


async def inbound_email(db: AsyncSession, *, sender: str, subject: str, body: str, thread_id: str = "") -> dict:
    p = None
    if thread_id:
        row = await _one(db, "SELECT prospect_id::text AS id FROM prospect_contacts WHERE gmail_thread_id = :t LIMIT 1", {"t": thread_id[:120]})
        if row:
            p = await prospect_by(db, "id", row["id"])
    if not p and sender:
        p = await prospect_by(db, "email", sender.strip().lower())
    if not p:
        return {"prospecto": None, "baja": False}
    negative = is_negative(body, subject)
    await log_contact(db, p["id"], "email", "respuesta", detail={"asunto": (subject or "")[:200], "no": negative,
                                                                "extracto": strip_quoted(body)[:400]})
    if negative:
        await unsubscribe(db, p, reason="respondio_no")
    else:
        await _promote(db, p["id"], "respondio", "replied_at")
        await db.execute(text("""UPDATE prospect_contacts SET status = 'cancelado' WHERE prospect_id = CAST(:i AS uuid)
                                 AND status IN ('pendiente', 'aprobado')"""), {"i": p["id"]})
        await db.commit()
    return {"prospecto": public_prospect(p, full_email=True), "baja": negative}


async def set_status(db: AsyncSession, prospect_id: str, status: str) -> dict:
    p = await prospect_by(db, "id", prospect_id)
    if not p:
        raise LookupError("no_existe")
    if status == "baja":
        await unsubscribe(db, p, reason="manual", channel="sistema")
    elif status in ("demo", "cliente"):
        if p["status"] == "baja":
            raise ValueError("esta_de_baja")
        await _promote(db, p["id"], status, "demo_at" if status == "demo" else "client_at")
        await log_contact(db, p["id"], "sistema", status)
        await db.commit()
    else:
        raise ValueError("estado_no_permitido")
    return public_prospect(await prospect_by(db, "id", prospect_id), full_email=True)


# ---------------------------------------------------------------- lote diario y envio
def _eligible_sql() -> str:
    return """NOT p.is_test AND p.email <> '' AND p.status NOT IN ('baja', 'respondio', 'demo', 'cliente')
              AND p.business_status IN ('', 'OPERATIONAL') AND p.replied_at IS NULL AND p.unsubscribed_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM prospect_exclusions x WHERE (x.kind = 'email' AND x.value = lower(p.email))
                              OR (x.kind = 'domain' AND x.value = split_part(lower(p.email), '@', 2))
                              OR (x.kind = 'place' AND x.value = p.place_id))
              AND (p.last_contacted_at IS NULL OR p.last_contacted_at < :week_ago)"""


async def build_batch(db: AsyncSession, at: Optional[datetime] = None) -> dict:
    """Lote del dia (idempotente por fecha). Seguimientos vencidos primero, luego correos nuevos."""
    b = bogota(at)
    day = b.date()
    existing = await _one(db, "SELECT * FROM prospect_batches WHERE local_date = :d", {"d": day})
    if existing:
        return await batch_view(db, existing["id"])
    if not is_business_day(day):
        return {"batch": None, "items": [], "motivo": "festivo" if day.weekday() < 5 else "fin_de_semana"}
    cfg = await get_settings(db)
    if b.hour >= int(cfg["window_end"]):
        return {"batch": None, "items": [], "motivo": "fuera_de_horario"}
    # lo aprobado o pendiente de dias anteriores que no salio, vence (vuelve a ser elegible)
    await db.execute(text("""UPDATE prospect_contacts SET status = 'vencido' WHERE status IN ('pendiente', 'aprobado')
                             AND batch_id IN (SELECT id FROM prospect_batches WHERE local_date < :d)"""), {"d": day})
    await db.execute(text("UPDATE prospect_batches SET status = 'vencido' WHERE local_date < :d AND status IN ('pendiente', 'aprobado')"), {"d": day})
    limit = int(cfg["daily_limit"])
    t = at or now()
    params = {"week_ago": t - timedelta(days=WEEK_DAYS), "follow_cut": t - timedelta(days=FOLLOWUP_DAYS), "lim": limit}
    follow = await _rows(db, f"""SELECT p.id::text AS id FROM prospects p WHERE {_eligible_sql()}
                                 AND p.contact_count = 1 AND p.followup_sent_at IS NULL AND p.first_contacted_at <= :follow_cut
                                 ORDER BY p.first_contacted_at LIMIT :lim""", params)
    params["lim"] = max(0, limit - len(follow))
    fresh = await _rows(db, f"""SELECT p.id::text AS id FROM prospects p LEFT JOIN prospect_zones z ON z.id = p.zone_id
                                WHERE {_eligible_sql()} AND p.contact_count = 0
                                ORDER BY z.sort NULLS LAST, p.created_at LIMIT :lim""", params) if params["lim"] else []
    if not follow and not fresh:
        return {"batch": None, "items": [], "motivo": "sin_prospectos"}
    row = await _one(db, """INSERT INTO prospect_batches (local_date, item_count, preview_token) VALUES (:d, :n, :t)
                            ON CONFLICT (local_date) DO NOTHING RETURNING id""",
                     {"d": day, "n": len(follow) + len(fresh), "t": secrets.token_urlsafe(24)})
    if not row:  # otro proceso lo creo al mismo tiempo
        await db.rollback()
        existing = await _one(db, "SELECT id FROM prospect_batches WHERE local_date = :d", {"d": day})
        return await batch_view(db, existing["id"])
    for kind, items in (("seguimiento", follow), ("inicial", fresh)):
        for it in items:
            p = await prospect_by(db, "id", it["id"])
            mail = pe.render(p, followup=kind == "seguimiento", settings=cfg, zone_slug=p.get("zone_slug") or "")
            await log_contact(db, p["id"], "email", kind, status="pendiente", batch_id=row["id"], to_email=p["email"],
                              subject=mail["subject"])
    await db.commit()
    return await batch_view(db, row["id"])


async def batch_view(db: AsyncSession, batch_id: int) -> dict:
    b = await _one(db, "SELECT id, local_date::text AS local_date, status, item_count, preview_token, approved_at FROM prospect_batches WHERE id = :i",
                   {"i": batch_id})
    if not b:
        raise LookupError("lote_no_existe")
    items = await _rows(db, """
        SELECT c.id, c.kind, c.status, c.to_email, c.subject, p.id::text AS prospect_id, p.name, p.business_type, z.name AS zona
        FROM prospect_contacts c JOIN prospects p ON p.id = c.prospect_id LEFT JOIN prospect_zones z ON z.id = p.zone_id
        WHERE c.batch_id = :i AND c.channel = 'email' ORDER BY c.id""", {"i": batch_id})
    for it in items:
        it["tipo"] = TYPE_LABEL.get(it["business_type"], it["business_type"])
    return {"batch": b, "items": items}


async def decide_batch(db: AsyncSession, batch_id: int, approve: bool, by: str = "telegram", at: Optional[datetime] = None) -> dict:
    b = await _one(db, "SELECT id, local_date, status FROM prospect_batches WHERE id = :i", {"i": batch_id})
    if not b:
        raise LookupError("lote_no_existe")
    if b["status"] != "pendiente":
        return {**(await batch_view(db, batch_id)), "cambio": False}
    if b["local_date"] != bogota(at).date():
        raise ValueError("lote_de_otro_dia")
    if approve:
        await db.execute(text("UPDATE prospect_batches SET status = 'aprobado', approved_at = now(), decided_by = :by WHERE id = :i"),
                         {"i": batch_id, "by": by[:40]})
        await db.execute(text("UPDATE prospect_contacts SET status = 'aprobado' WHERE batch_id = :i AND status = 'pendiente'"), {"i": batch_id})
    else:
        await db.execute(text("UPDATE prospect_batches SET status = 'saltado', decided_by = :by WHERE id = :i"), {"i": batch_id, "by": by[:40]})
        await db.execute(text("UPDATE prospect_contacts SET status = 'saltado' WHERE batch_id = :i AND status = 'pendiente'"), {"i": batch_id})
    await db.commit()
    return {**(await batch_view(db, batch_id)), "cambio": True}


async def claim_next(db: AsyncSession, at: Optional[datetime] = None) -> dict:
    """El siguiente correo APROBADO de hoy, si se puede enviar ya. Revisa todo otra vez al momento."""
    cfg = await get_settings(db)
    t = at or now()
    if not in_legal_window(t, int(cfg["window_start"]), int(cfg["window_end"])):
        return {"item": None, "motivo": "fuera_de_horario"}
    # un envio que quedo a medias (n8n se cayo) no se repite: queda fallido
    await db.execute(text("""UPDATE prospect_contacts SET status = 'fallido', detail = detail || '{"motivo": "sin_confirmacion"}'::jsonb
                             WHERE status = 'enviando' AND claimed_at < :c"""), {"c": t - timedelta(minutes=STALE_CLAIM_MIN)})
    last = await _one(db, """SELECT MAX(GREATEST(COALESCE(sent_at, 'epoch'), COALESCE(claimed_at, 'epoch'))) AS at FROM prospect_contacts
                             WHERE channel = 'email' AND status IN ('enviado', 'enviando')""")
    if last and last["at"] and last["at"] > t - timedelta(minutes=int(cfg["min_gap_minutes"])):
        await db.commit()
        return {"item": None, "motivo": "espaciado"}
    day = bogota(t).date()
    params = {"d": day, "week_ago": t - timedelta(days=WEEK_DAYS)}
    while True:
        c = await _one(db, """
            SELECT c.id, c.kind, c.prospect_id::text AS prospect_id, c.batch_id FROM prospect_contacts c
            JOIN prospect_batches b ON b.id = c.batch_id
            WHERE b.local_date = :d AND b.status = 'aprobado' AND c.status = 'aprobado' AND c.channel = 'email'
            ORDER BY c.id LIMIT 1 FOR UPDATE OF c SKIP LOCKED""", params)
        if not c:
            await db.commit()
            return {"item": None, "motivo": "nada_pendiente"}
        ok = await _one(db, f"SELECT p.id FROM prospects p WHERE p.id = CAST(:pid AS uuid) AND {_eligible_sql()} AND p.contact_count < :max",
                        {**params, "pid": c["prospect_id"], "max": MAX_EMAILS})
        if c["kind"] == "seguimiento":
            ok = ok and await _one(db, "SELECT 1 AS x FROM prospects WHERE id = CAST(:i AS uuid) AND followup_sent_at IS NULL AND contact_count = 1",
                                   {"i": c["prospect_id"]})
        if not ok:
            await db.execute(text("UPDATE prospect_contacts SET status = 'cancelado' WHERE id = :i"), {"i": c["id"]})
            continue
        p = await prospect_by(db, "id", c["prospect_id"])
        mail = pe.render(p, followup=c["kind"] == "seguimiento", settings=cfg, zone_slug=p.get("zone_slug") or "")
        await db.execute(text("UPDATE prospect_contacts SET status = 'enviando', claimed_at = :t, to_email = :to, subject = :s WHERE id = :i"),
                         {"i": c["id"], "t": t, "to": p["email"], "s": mail["subject"]})
        await db.commit()
        return {"item": {"contact_id": c["id"], "kind": c["kind"], "prospect": p["name"], "to": p["email"], "subject": mail["subject"],
                         "html": mail["html"], "text": mail["text"], "sender_name": cfg["sender_name"],
                         "reply_to": cfg["reply_to"] or ""}, "motivo": ""}


async def mark_sent(db: AsyncSession, contact_id: int, *, message_id: str = "", thread_id: str = "",
                    at: Optional[datetime] = None) -> dict:
    c = await _one(db, "SELECT id, prospect_id::text AS pid, kind, status FROM prospect_contacts WHERE id = :i", {"i": contact_id})
    if not c:
        raise LookupError("no_existe")
    if c["status"] == "enviado":
        return {"ok": True, "repetido": True}
    if c["status"] not in ("enviando", "fallido"):
        raise ValueError("no_estaba_en_envio")
    t = at or now()
    await db.execute(text("""UPDATE prospect_contacts SET status = 'enviado', sent_at = :at, gmail_message_id = :m, gmail_thread_id = :t
                             WHERE id = :i"""), {"i": contact_id, "m": (message_id or "")[:120], "t": (thread_id or "")[:120], "at": t})
    follow = ", followup_sent_at = :at" if c["kind"] == "seguimiento" else ""
    await db.execute(text(f"""UPDATE prospects SET contact_count = contact_count + 1, last_contacted_at = :at,
                              first_contacted_at = COALESCE(first_contacted_at, :at){follow}, updated_at = now()
                              WHERE id = CAST(:p AS uuid)"""), {"p": c["pid"], "at": t})
    await _promote(db, c["pid"], "contactado")
    await db.commit()
    return {"ok": True, "repetido": False}


async def mark_failed(db: AsyncSession, contact_id: int, error: str = "") -> dict:
    await db.execute(text("""UPDATE prospect_contacts SET status = 'fallido', detail = detail || CAST(:d AS jsonb)
                             WHERE id = :i AND status = 'enviando'"""), {"i": contact_id, "d": json.dumps({"error": (error or "")[:300]})})
    await db.commit()
    return {"ok": True}


async def preview_html(db: AsyncSession, batch_id: int, token: str) -> Optional[str]:
    b = await _one(db, "SELECT id, preview_token, created_at FROM prospect_batches WHERE id = :i", {"i": batch_id})
    if not b or not secrets.compare_digest(b["preview_token"], token or "") or b["created_at"] < now() - timedelta(days=2):
        return None
    c = await _one(db, "SELECT prospect_id::text AS pid, kind FROM prospect_contacts WHERE batch_id = :i ORDER BY id LIMIT 1", {"i": batch_id})
    if not c:
        return None
    p = await prospect_by(db, "id", c["pid"])
    cfg = await get_settings(db)
    return pe.render(p, followup=c["kind"] == "seguimiento", settings=cfg, zone_slug=p.get("zone_slug") or "")["html"]


async def ensure_test_prospects(db: AsyncSession, recipient: str) -> list[dict]:
    """Un prospecto de PRUEBA por plantilla (is_test: no sale en el mapa ni en los lotes), con el correo de
    Clonexa + etiqueta (recipient+carta@...), para probar baja y enlaces sin tocar negocios reales."""
    local, domain = recipient.split("@", 1)
    out = []
    zone = await _one(db, "SELECT id FROM prospect_zones WHERE slug = 'kennedy-central'") or {}
    for seg, btype in (("carta", "restaurante"), ("bar", "bar"), ("taller", "taller")):
        pid = f"clonexa-prueba-{seg}"
        email = f"{local}+{seg}@{domain}"
        row = await _one(db, "SELECT id::text AS id FROM prospects WHERE place_id = :p", {"p": pid})
        if not row:
            row = await _one(db, """INSERT INTO prospects (place_id, code, unsub_token, name, business_type, zone_id, email, email_status,
                                    email_source_url, is_test, lat, lng)
                                    VALUES (:p, :c, :t, :n, :b, :z, :e, 'encontrado', 'prueba', true, 4.62171, -74.15262)
                                    RETURNING id::text AS id""",
                                 {"p": pid, "c": await _unique_code(db), "t": secrets.token_urlsafe(24),
                                  "n": {"carta": "Restaurante de Prueba", "bar": "Bar de Prueba", "taller": "Taller de Prueba"}[seg],
                                  "b": btype, "z": zone.get("id"), "e": email})
        out.append(await prospect_by(db, "id", row["id"]))
    await db.commit()
    return out


async def test_emails(db: AsyncSession, recipient: str) -> list[dict]:
    """Los 3 correos de ejemplo, SOLO al correo de Clonexa. Si una prueba se dio de baja, no se envia
    (asi se comprueba que la baja bloquea envios futuros)."""
    cfg = await get_settings(db)
    out = []
    for p in await ensure_test_prospects(db, recipient):
        if p["status"] == "baja" or await _excluded(db, email=p["email"]):
            out.append({"prospect": p["name"], "to": p["email"], "bloqueado": True})
            continue
        mail = pe.render(p, followup=False, settings=cfg, zone_slug=p.get("zone_slug") or "kennedy-central")
        cid = await log_contact(db, p["id"], "email", "prueba", status="enviando", to_email=p["email"], subject=mail["subject"])
        await db.execute(text("UPDATE prospect_contacts SET claimed_at = now() WHERE id = :i"), {"i": cid})
        out.append({"contact_id": cid, "prospect": p["name"], "to": p["email"], "subject": "[PRUEBA] " + mail["subject"],
                    "html": mail["html"], "sender_name": cfg["sender_name"], "bloqueado": False,
                    "demo_url": mail["demo_url"], "wa_url": mail["wa_url"], "unsub_url": mail["unsub_url"]})
    await db.commit()
    return out


# ---------------------------------------------------------------- consola (mapa comercial)
def public_prospect(p: Optional[dict], *, full_email: bool = False) -> Optional[dict]:
    if not p:
        return None
    out = {k: p.get(k) for k in ("id", "code", "name", "business_type", "address", "neighborhood", "zone_id", "zone_name",
                                 "zone_group", "lat", "lng", "status", "contact_count", "email_status", "website", "phone")}
    for k in ("first_contacted_at", "last_contacted_at", "followup_sent_at", "opened_at", "replied_at", "demo_at", "client_at",
              "unsubscribed_at", "wa_consent_at", "created_at", "place_refreshed_at"):
        v = p.get(k)
        out[k] = v.isoformat() if isinstance(v, datetime) else v
    out["tipo"] = TYPE_LABEL.get(p.get("business_type"), p.get("business_type"))
    out["estado"] = STATUS_LABEL.get(p.get("status"), p.get("status"))
    out["email"] = (p.get("email") or "") if full_email else mask_email(p.get("email") or "")
    out["email_source_url"] = p.get("email_source_url") if full_email else ""
    out["maps_url"] = ("https://www.google.com/maps/search/?api=1&query=" + _q(p.get("name") or "") +
                       "&query_place_id=" + _q(p.get("place_id") or ""))
    return out


def _q(v: str) -> str:
    from urllib.parse import quote
    return quote(str(v), safe="")


def _filters(f: dict) -> tuple[str, dict]:
    where, params = ["NOT p.is_test"], {}
    if f.get("zone_id"):
        where.append("p.zone_id = :zone_id")
        params["zone_id"] = int(f["zone_id"])
    if f.get("type") in TYPES:
        where.append("p.business_type = :btype")
        params["btype"] = f["type"]
    if f.get("status") in STATUSES:
        where.append("p.status = :status")
        params["status"] = f["status"]
    if f.get("desde"):
        where.append("p.created_at >= CAST(:desde AS date)")
        params["desde"] = f["desde"]
    if f.get("hasta"):
        where.append("p.created_at < CAST(:hasta AS date) + 1")
        params["hasta"] = f["hasta"]
    return " AND ".join(where), params


def zone_score(c: dict) -> int:
    """Puntaje de importancia de una zona: lo que mas pesa es lo que esta mas cerca de ser cliente."""
    return int(c.get("prospectos", 0) * 1 + c.get("enviados", 0) * 2 + c.get("abrieron", 0) * 5 + c.get("respondieron", 0) * 10
               + c.get("demos", 0) * 20 + c.get("clientes", 0) * 40)


async def map_data(db: AsyncSession, f: dict) -> dict:
    where, params = _filters(f)
    pins = await _rows(db, f"""SELECT p.id::text AS id, p.name, p.business_type, p.status, p.lat, p.lng, p.zone_id, p.email
                               FROM prospects p WHERE {where} AND p.lat IS NOT NULL ORDER BY p.created_at DESC LIMIT 3000""", params)
    for pin in pins:
        pin["email"] = mask_email(pin["email"])
        pin["tipo"] = TYPE_LABEL.get(pin["business_type"], pin["business_type"])
    sent_where = "c.channel = 'email' AND c.status = 'enviado' AND c.kind IN ('inicial', 'seguimiento')"
    counts = await _rows(db, f"""
        SELECT p.zone_id, COUNT(DISTINCT p.id)::int AS prospectos,
               COUNT(DISTINCT p.id) FILTER (WHERE p.email <> '')::int AS con_correo,
               (SELECT COUNT(*) FROM prospect_contacts c JOIN prospects q ON q.id = c.prospect_id
                WHERE q.zone_id = p.zone_id AND {sent_where} AND NOT q.is_test)::int AS enviados,
               COUNT(DISTINCT p.id) FILTER (WHERE p.opened_at IS NOT NULL)::int AS abrieron,
               COUNT(DISTINCT p.id) FILTER (WHERE p.replied_at IS NOT NULL)::int AS respondieron,
               COUNT(DISTINCT p.id) FILTER (WHERE p.demo_at IS NOT NULL)::int AS demos,
               COUNT(DISTINCT p.id) FILTER (WHERE p.client_at IS NOT NULL)::int AS clientes,
               COUNT(DISTINCT p.id) FILTER (WHERE p.status = 'baja')::int AS bajas
        FROM prospects p WHERE {where} GROUP BY p.zone_id""", params)
    by_zone = {c["zone_id"]: c for c in counts}
    zone_list = []
    for z in await zones(db):
        c = by_zone.get(z["id"], {})
        stats = {k: c.get(k, 0) for k in ("prospectos", "con_correo", "enviados", "abrieron", "respondieron", "demos", "clientes", "bajas")}
        zone_list.append({**z, **stats, "puntaje": zone_score(stats),
                          "pct_abrio": round(100 * stats["abrieron"] / stats["enviados"], 1) if stats["enviados"] else 0,
                          "pct_respondio": round(100 * stats["respondieron"] / stats["enviados"], 1) if stats["enviados"] else 0})
    totals = {k: sum(c.get(k, 0) for c in counts) for k in ("prospectos", "con_correo", "enviados", "abrieron", "respondieron", "demos", "clientes", "bajas")}
    visit_where = ["lat IS NOT NULL"]
    vparams: dict[str, Any] = {}
    if f.get("desde"):
        visit_where.append("created_at >= CAST(:desde AS date)")
        vparams["desde"] = f["desde"]
    if f.get("hasta"):
        visit_where.append("created_at < CAST(:hasta AS date) + 1")
        vparams["hasta"] = f["hasta"]
    if not f.get("desde") and not f.get("hasta"):
        visit_where.append("created_at >= now() - interval '90 days'")
    heat_visits = await _rows(db, f"""
        SELECT COALESCE(NULLIF(city, ''), 'Sin ciudad') AS city, COALESCE(NULLIF(region, ''), '') AS region, country,
               ROUND(AVG(lat)::numeric, 4)::float AS lat, ROUND(AVG(lng)::numeric, 4)::float AS lng, COUNT(*)::int AS total
        FROM landing_visit_events WHERE {' AND '.join(visit_where)}
        GROUP BY 1, 2, 3 ORDER BY total DESC LIMIT 300""", vparams) if await _has_geo_columns(db) else []
    heat_leads = await _rows(db, f"""
        SELECT ROUND(p.lat::numeric, 3)::float AS lat, ROUND(p.lng::numeric, 3)::float AS lng, COUNT(*)::int AS total
        FROM prospects p WHERE {where} AND p.lat IS NOT NULL AND (p.replied_at IS NOT NULL OR p.demo_at IS NOT NULL OR p.client_at IS NOT NULL)
        GROUP BY 1, 2 ORDER BY total DESC LIMIT 500""", params)
    return {"pins": pins, "zones": zone_list, "heat_visits": heat_visits, "heat_leads": heat_leads, "cards": totals,
            "types": [{"key": k, "label": v} for k, v in TYPE_LABEL.items()],
            "statuses": [{"key": k, "label": v} for k, v in STATUS_LABEL.items()]}


async def _has_geo_columns(db: AsyncSession) -> bool:
    row = await _one(db, """SELECT COUNT(*)::int AS n FROM information_schema.columns
                            WHERE table_name = 'landing_visit_events' AND column_name IN ('lat', 'lng')""")
    return bool(row and row["n"] == 2)


async def prospect_detail(db: AsyncSession, prospect_id: str, *, full_email: bool) -> Optional[dict]:
    p = await prospect_by(db, "id", prospect_id)
    if not p or p["is_test"]:
        return None
    history = await _rows(db, """SELECT id, channel, kind, status, subject, sent_at, created_at, detail FROM prospect_contacts
                                 WHERE prospect_id = CAST(:i AS uuid) ORDER BY created_at DESC LIMIT 60""", {"i": prospect_id})
    for h in history:
        for k in ("sent_at", "created_at"):
            if isinstance(h[k], datetime):
                h[k] = h[k].isoformat()
        d = h.get("detail") or {}
        h["detail"] = {k: d[k] for k in ("motivo", "no", "campana", "primera", "primera_vez", "asunto", "error") if k in d}
    return {"prospect": public_prospect(p, full_email=full_email), "history": history}
