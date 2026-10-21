"""Redes sociales de Nexa (consola v2+ -> Landing -> Redes sociales).

- POST /ingest: lo llama n8n (Nexa) con la cabecera X-Nexa-Token. No es una
  sesion de usuario: es un token de servicio (NEXA_INGEST_TOKEN) comparado en
  tiempo constante. Sin la variable 503, token mal 401, 60 peticiones por minuto
  por IP. Nunca se registra ni se devuelve el token.
- GET /summary: solo Admin V2. Cifras por red, publicaciones, embudo hacia la
  landing (visitas con utm_source de redes o referrer de dominios de redes) y
  visitas por campana nexa-*.

Las tablas son de la propia Clonexa (sin company_id) y las crea la migracion
024r_social_metrics; aqui no hay DDL.
"""
from __future__ import annotations

import hmac
import json
import os
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.web import admin_v2_routes

router = APIRouter()

NETWORKS = ("instagram", "facebook", "youtube", "linkedin", "tiktok")
NETWORK_LABELS = {"instagram": "Instagram", "facebook": "Facebook", "youtube": "YouTube", "linkedin": "LinkedIn", "tiktok": "TikTok"}
# Dominios de referrer que cuentan como "llego desde la red". www. y m. se quitan antes.
SOCIAL_DOMAINS = {
    "instagram": ("instagram.com", "l.instagram.com"),
    "facebook": ("facebook.com", "l.facebook.com", "lm.facebook.com"),
    "youtube": ("youtube.com", "youtu.be"),
    "linkedin": ("linkedin.com", "lnkd.in"),
    "tiktok": ("tiktok.com",),
}
TOKEN_ENV = "NEXA_INGEST_TOKEN"
MAX_ITEMS = 200
MAX_BODY = 2_000_000
MAX_RAW = 8_000  # caracteres de raw por elemento; mas grande se guarda solo el aviso
MAX_INT = 2_147_483_647
BOGOTA = timezone(timedelta(hours=-5))  # Colombia no tiene horario de verano

Network = Literal["instagram", "facebook", "youtube", "linkedin", "tiktok"]
Count = Annotated[Optional[int], Field(default=None, ge=0, le=MAX_INT)]


# ---------------------------------------------------------------- limite (un solo worker)
class _RateLimit:
    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        if len(self.hits) > 5000:
            for k in [k for k, v in list(self.hits.items()) if not v][:2500]:
                self.hits.pop(k, None)
        return True


INGEST_PER_IP = _RateLimit(60, 60.0)


def _ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    return (forwarded.split(",")[0].strip() or (request.client.host if request.client else "") or "?")[:64]


def require_nexa_token(request: Request) -> None:
    """Token de servicio de n8n. El orden importa: limite, variable, token."""
    if not INGEST_PER_IP.allow(_ip(request)):
        raise HTTPException(status_code=429, detail="too_many_requests")
    expected = os.getenv(TOKEN_ENV, "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="ingest_not_configured")
    given = (request.headers.get("x-nexa-token") or "").strip()
    if not given or not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="invalid_token")


async def require_admin_v2_session(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    if not await admin_v2_routes._active_session(request, db):
        raise HTTPException(status_code=401, detail="admin_v2_session_required")


# ---------------------------------------------------------------- cuerpo del ingest
def _trim(limit: int):
    def run(value: Any) -> Any:
        if value is None:
            return None
        value = str(value).strip()
        return value[:limit] or None
    return run


class _Item(BaseModel):
    model_config = ConfigDict(extra="ignore")

    network: Network
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("network", mode="before")
    @classmethod
    def _network(cls, value: Any) -> Any:
        return str(value or "").strip().lower()

    @field_validator("raw", mode="before")
    @classmethod
    def _raw(cls, value: Any) -> Any:
        return {} if value is None else value


class SnapshotIn(_Item):
    metric_date: date
    followers: Count = None
    impressions: Count = None
    reach: Count = None
    views: Count = None
    engagements: Count = None
    posts_count: Count = None


class PostIn(_Item):
    external_id: str = Field(min_length=1, max_length=200)
    url: Optional[str] = Field(default=None, max_length=2000)
    published_at: Optional[datetime] = None
    tema: Optional[str] = None
    caption: Optional[str] = None
    video_id_heygen: Optional[str] = Field(default=None, max_length=200)
    utm_campaign: Optional[str] = Field(default=None, max_length=220)
    views: Count = None
    likes: Count = None
    comments: Count = None
    shares: Count = None
    saves: Count = None
    reach: Count = None

    _tema = field_validator("tema", mode="before")(_trim(300))
    _caption = field_validator("caption", mode="before")(_trim(600))

    @field_validator("external_id", mode="before")
    @classmethod
    def _external(cls, value: Any) -> Any:
        return str(value).strip() if value is not None else value


class IngestIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    snapshots: list[SnapshotIn] = Field(default_factory=list, max_length=MAX_ITEMS)
    posts: list[PostIn] = Field(default_factory=list, max_length=MAX_ITEMS)

    @field_validator("snapshots", "posts", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> Any:
        return [] if value is None else value


def _raw_json(raw: dict[str, Any]) -> str:
    dumped = json.dumps(raw or {}, ensure_ascii=False, default=str)
    if len(dumped) > MAX_RAW:
        return json.dumps({"_omitido": f"raw de {len(dumped)} caracteres (maximo {MAX_RAW})"})
    return dumped


def _errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [{"loc": list(e.get("loc", ())), "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))} for e in exc.errors()]


async def parse_ingest(request: Request) -> IngestIn:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(status_code=413, detail="body_too_large")
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail=[{"loc": ["body"], "msg": "JSON invalido", "type": "json_invalid"}])
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail=[{"loc": ["body"], "msg": "Se espera un objeto", "type": "dict_type"}])
    try:
        return IngestIn.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_errors(exc))


# Si un numero llega null, no borra lo que ya habia; raw vacio tampoco.
UPSERT_SNAPSHOT = """
    INSERT INTO social_daily_metrics (network, metric_date, followers, impressions, reach, views, engagements, posts_count, raw)
    VALUES (:network, :metric_date, :followers, :impressions, :reach, :views, :engagements, :posts_count, CAST(:raw AS jsonb))
    ON CONFLICT (network, metric_date) DO UPDATE SET
        followers = COALESCE(EXCLUDED.followers, social_daily_metrics.followers),
        impressions = COALESCE(EXCLUDED.impressions, social_daily_metrics.impressions),
        reach = COALESCE(EXCLUDED.reach, social_daily_metrics.reach),
        views = COALESCE(EXCLUDED.views, social_daily_metrics.views),
        engagements = COALESCE(EXCLUDED.engagements, social_daily_metrics.engagements),
        posts_count = COALESCE(EXCLUDED.posts_count, social_daily_metrics.posts_count),
        raw = CASE WHEN EXCLUDED.raw = '{}'::jsonb THEN social_daily_metrics.raw ELSE EXCLUDED.raw END,
        updated_at = now()
"""
UPSERT_POST = """
    INSERT INTO social_posts (network, external_id, url, published_at, tema, caption, video_id_heygen, utm_campaign,
                              views, likes, comments, shares, saves, reach, raw)
    VALUES (:network, :external_id, :url, :published_at, :tema, :caption, :video_id_heygen, :utm_campaign,
            :views, :likes, :comments, :shares, :saves, :reach, CAST(:raw AS jsonb))
    ON CONFLICT (network, external_id) DO UPDATE SET
        url = COALESCE(EXCLUDED.url, social_posts.url),
        published_at = COALESCE(EXCLUDED.published_at, social_posts.published_at),
        tema = COALESCE(EXCLUDED.tema, social_posts.tema),
        caption = COALESCE(EXCLUDED.caption, social_posts.caption),
        video_id_heygen = COALESCE(EXCLUDED.video_id_heygen, social_posts.video_id_heygen),
        utm_campaign = COALESCE(EXCLUDED.utm_campaign, social_posts.utm_campaign),
        views = COALESCE(EXCLUDED.views, social_posts.views),
        likes = COALESCE(EXCLUDED.likes, social_posts.likes),
        comments = COALESCE(EXCLUDED.comments, social_posts.comments),
        shares = COALESCE(EXCLUDED.shares, social_posts.shares),
        saves = COALESCE(EXCLUDED.saves, social_posts.saves),
        reach = COALESCE(EXCLUDED.reach, social_posts.reach),
        raw = CASE WHEN EXCLUDED.raw = '{}'::jsonb THEN social_posts.raw ELSE EXCLUDED.raw END,
        updated_at = now()
"""


@router.post("/ingest", include_in_schema=False)
async def ingest(request: Request, _: None = Depends(require_nexa_token), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    body = await parse_ingest(request)
    for s in body.snapshots:
        await db.execute(text(UPSERT_SNAPSHOT), {
            "network": s.network, "metric_date": s.metric_date, "followers": s.followers, "impressions": s.impressions,
            "reach": s.reach, "views": s.views, "engagements": s.engagements, "posts_count": s.posts_count, "raw": _raw_json(s.raw),
        })
    for p in body.posts:
        published = p.published_at
        if published is not None and published.tzinfo is None:
            published = published.replace(tzinfo=BOGOTA)
        await db.execute(text(UPSERT_POST), {
            "network": p.network, "external_id": p.external_id, "url": p.url, "published_at": published, "tema": p.tema,
            "caption": p.caption, "video_id_heygen": p.video_id_heygen, "utm_campaign": p.utm_campaign, "views": p.views,
            "likes": p.likes, "comments": p.comments, "shares": p.shares, "saves": p.saves, "reach": p.reach, "raw": _raw_json(p.raw),
        })
    await db.commit()
    return {"ok": True, "snapshots": len(body.snapshots), "posts": len(body.posts)}


# ---------------------------------------------------------------- de donde viene una visita
def _bare_domain(domain: str) -> str:
    d = str(domain or "").strip().lower().split(":", 1)[0]
    for prefix in ("www.", "m."):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d


def network_of(source: str, referrer_domain: str = "") -> Optional[str]:
    """Red de una visita: primero utm_source, luego el dominio del referrer.
    `source` de la landing es utm_source o, sin el, el dominio del referrer."""
    s = str(source or "").strip().lower()
    if s in NETWORKS:
        return s
    for value in (s, referrer_domain):
        bare = _bare_domain(value)
        for network, domains in SOCIAL_DOMAINS.items():
            if bare in domains:
                return network
    return None


def _domain_sql(column: str) -> str:
    return f"regexp_replace(split_part(lower(btrim({column})), ':', 1), '^(www|m)\\.', '')"


def network_case_sql() -> str:
    """El mismo criterio de network_of en SQL (solo constantes de este archivo)."""
    utm = " ".join(f"WHEN lower(btrim(source)) = '{n}' THEN '{n}'" for n in NETWORKS)
    by_domain = []
    for column in ("source", "referrer_domain"):
        for network, domains in SOCIAL_DOMAINS.items():
            listed = ", ".join(f"'{d}'" for d in domains)
            by_domain.append(f"WHEN {_domain_sql(column)} IN ({listed}) THEN '{network}'")
    return f"CASE {utm} {' '.join(by_domain)} END"


# ---------------------------------------------------------------- resumen
def _today() -> date:
    return datetime.now(BOGOTA).date()


def _sum(values) -> Optional[int]:
    present = [int(v) for v in values if v is not None]
    return sum(present) if present else None


def build_networks(rows: list[dict], latest: dict[str, dict], baseline: dict[str, dict], posts: dict[str, dict],
                   start: date, today: date) -> list[dict]:
    """Una tarjeta por red. rows: cifras diarias del periodo; latest/baseline:
    ultimo seguidor conocido (hasta hoy / hasta el inicio); posts: agregados
    de publicaciones del periodo."""
    by_net: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_net[r["network"]].append(r)
    out = []
    for n in NETWORKS:
        days = sorted(by_net.get(n, []), key=lambda r: r["metric_date"])
        agg = posts.get(n) or {}
        current = (latest.get(n) or {}).get("followers")
        first_in_period = next((r["followers"] for r in days if r["followers"] is not None), None)
        base = (baseline.get(n) or {}).get("followers")
        base = base if base is not None else first_in_period
        views = _sum(r["views"] for r in days)
        if views is None:
            views = agg.get("views")
        engagements = _sum(r["engagements"] for r in days)
        if engagements is None:
            engagements = agg.get("interactions")
        post_count = int(agg.get("posts") or 0) or (_sum(r["posts_count"] for r in days) or 0)
        series_map = {r["metric_date"]: r for r in days}
        series = []
        d = start
        while d <= today:
            r = series_map.get(d) or {}
            series.append({"date": d.isoformat(), "followers": r.get("followers"), "views": r.get("views")})
            d += timedelta(days=1)
        out.append({
            "network": n, "label": NETWORK_LABELS[n],
            "has_data": bool(days or agg.get("posts") or current is not None),
            "followers": current,
            "followers_change": (current - base) if current is not None and base is not None else None,
            "views": views or 0, "engagements": engagements or 0, "posts": post_count, "series": series,
        })
    return out


async def _table_exists(db: AsyncSession, name: str) -> bool:
    return bool((await db.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": f"public.{name}"})).scalar())


async def _rows(db: AsyncSession, sql: str, params: dict) -> list[dict]:
    return [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]


@router.get("/summary")
async def summary(
    days: int = Query(default=30),
    _: None = Depends(require_admin_v2_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if days not in (7, 30, 90):
        raise HTTPException(status_code=422, detail="days debe ser 7, 30 o 90")
    today = _today()
    start = today - timedelta(days=days - 1)
    start_ts = datetime(start.year, start.month, start.day, tzinfo=BOGOTA)
    p = {"start": start, "today": today, "start_ts": start_ts}

    rows = await _rows(db, """
        SELECT network, metric_date, followers, views, engagements, posts_count
        FROM social_daily_metrics WHERE metric_date BETWEEN :start AND :today
    """, p)
    latest = {r["network"]: r for r in await _rows(db, """
        SELECT DISTINCT ON (network) network, followers FROM social_daily_metrics
        WHERE followers IS NOT NULL AND metric_date <= :today ORDER BY network, metric_date DESC
    """, p)}
    baseline = {r["network"]: r for r in await _rows(db, """
        SELECT DISTINCT ON (network) network, followers FROM social_daily_metrics
        WHERE followers IS NOT NULL AND metric_date <= :start ORDER BY network, metric_date DESC
    """, p)}
    in_period = "COALESCE(published_at, created_at) >= :start_ts"
    post_agg = {r["network"]: r for r in await _rows(db, f"""
        SELECT network, COUNT(*)::int AS posts, SUM(views)::bigint AS views,
               SUM(COALESCE(likes, 0) + COALESCE(comments, 0) + COALESCE(shares, 0) + COALESCE(saves, 0))::bigint AS interactions
        FROM social_posts WHERE {in_period} GROUP BY network
    """, p)}
    posts = await _rows(db, f"""
        SELECT network, COALESCE(published_at, created_at) AS published_at, tema, url, utm_campaign,
               views, likes, comments, shares
        FROM social_posts WHERE {in_period}
        ORDER BY COALESCE(published_at, created_at) DESC LIMIT 200
    """, p)
    for item in posts:
        item["published_at"] = item["published_at"].isoformat() if item["published_at"] else None
        item["label"] = NETWORK_LABELS.get(item["network"], item["network"])

    networks = build_networks(rows, latest, baseline, post_agg, start, today)

    by_network: list[dict] = []
    campaigns: list[dict] = []
    landing = {"visits": 0, "unique_visitors": 0}
    if await _table_exists(db, "landing_visit_events"):
        social = f"""
            WITH v AS (
                SELECT visitor_id, {network_case_sql()} AS network
                FROM landing_visit_events WHERE created_at >= :start_ts
            )
        """
        total = (await db.execute(text(social + """
            SELECT COUNT(*)::int AS visits, COUNT(DISTINCT NULLIF(visitor_id, ''))::int AS unique_visitors
            FROM v WHERE network IS NOT NULL
        """), p)).mappings().first()
        landing = {"visits": int(total["visits"] or 0), "unique_visitors": int(total["unique_visitors"] or 0)}
        by_network = await _rows(db, social + """
            SELECT network, COUNT(*)::int AS visits, COUNT(DISTINCT NULLIF(visitor_id, ''))::int AS unique_visitors
            FROM v WHERE network IS NOT NULL GROUP BY network ORDER BY visits DESC, network
        """, p)
        for item in by_network:
            item["label"] = NETWORK_LABELS[item["network"]]
        campaigns = await _rows(db, """
            SELECT campaign, COUNT(*)::int AS visits, COUNT(DISTINCT NULLIF(visitor_id, ''))::int AS unique_visitors
            FROM landing_visit_events
            WHERE created_at >= :start_ts AND lower(campaign) LIKE 'nexa-%'
            GROUP BY campaign ORDER BY campaign DESC
        """, p)

    return {
        "ok": True, "days": days, "start": start.isoformat(), "end": today.isoformat(),
        "networks": networks,
        "posts": posts,
        "funnel": {"social_views": sum(n["views"] for n in networks), "landing_visits": landing["visits"], "unique_visitors": landing["unique_visitors"]},
        "landing_by_network": by_network,
        "landing_by_campaign": campaigns,
    }
