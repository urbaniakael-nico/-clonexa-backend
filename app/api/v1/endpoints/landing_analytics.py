from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, unquote_plus, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.web.admin_v2_routes import _valid_session

router = APIRouter()

LANDING_TRACKING_ENDPOINT = "https://clonexa-backend-production.up.railway.app/api/v1/landing-analytics/events"


class LandingEventIn(BaseModel):
    event_type: str = Field(default="page_view", max_length=80)
    url: str = Field(default="", max_length=1200)
    path: str = Field(default="", max_length=420)
    title: str = Field(default="", max_length=260)
    referrer: str = Field(default="", max_length=1200)
    visitor_id: str = Field(default="", max_length=120)
    session_id: str = Field(default="", max_length=120)
    utm_source: str = Field(default="", max_length=160)
    utm_medium: str = Field(default="", max_length=160)
    utm_campaign: str = Field(default="", max_length=220)
    utm_term: str = Field(default="", max_length=220)
    utm_content: str = Field(default="", max_length=220)
    language: str = Field(default="", max_length=80)
    timezone: str = Field(default="", max_length=120)
    platform: str = Field(default="", max_length=160)
    device: str = Field(default="", max_length=80)
    screen: str = Field(default="", max_length=80)
    viewport: str = Field(default="", max_length=80)
    extra: dict[str, Any] = Field(default_factory=dict)


def _clean(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_query_value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return _clean(values[0] if values else "", 220)


def _domain(value: str) -> str:
    try:
        return _clean(urlparse(value).netloc.lower(), 220)
    except Exception:
        return ""


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return _clean(forwarded.split(",")[0], 80)
    return _clean(getattr(request.client, "host", "") if request.client else "", 80)


def _country_from_headers(request: Request) -> str:
    for key in ("cf-ipcountry", "x-vercel-ip-country", "x-country-code", "cloudfront-viewer-country"):
        value = request.headers.get(key)
        if value:
            return _clean(value, 20).upper()
    return ""


def _header_geo_value(request: Request, keys: tuple[str, ...], limit: int = 120) -> str:
    for key in keys:
        value = request.headers.get(key)
        if value:
            return _clean(unquote_plus(value), limit)
    return ""


def _city_from_headers(request: Request) -> str:
    return _header_geo_value(
        request,
        (
            "cf-ipcity",
            "x-vercel-ip-city",
            "x-city",
            "x-appengine-city",
            "cloudfront-viewer-city",
        ),
    )


def _region_from_headers(request: Request) -> str:
    return _header_geo_value(
        request,
        (
            "cf-region",
            "x-vercel-ip-country-region",
            "x-region",
            "x-appengine-region",
            "cloudfront-viewer-country-region",
        ),
    )


def _source_label(event: LandingEventIn) -> str:
    if event.utm_source:
        return event.utm_source
    ref_domain = _domain(event.referrer)
    if ref_domain:
        return ref_domain
    return "directo"


async def _ensure_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS landing_visit_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_type VARCHAR(80) NOT NULL DEFAULT 'page_view',
            landing_url TEXT NOT NULL DEFAULT '',
            path TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            referrer TEXT NOT NULL DEFAULT '',
            referrer_domain VARCHAR(220) NOT NULL DEFAULT '',
            source VARCHAR(220) NOT NULL DEFAULT '',
            medium VARCHAR(180) NOT NULL DEFAULT '',
            campaign VARCHAR(260) NOT NULL DEFAULT '',
            term VARCHAR(260) NOT NULL DEFAULT '',
            content VARCHAR(260) NOT NULL DEFAULT '',
            visitor_id VARCHAR(140) NOT NULL DEFAULT '',
            session_id VARCHAR(140) NOT NULL DEFAULT '',
            ip_address VARCHAR(80) NOT NULL DEFAULT '',
            country VARCHAR(20) NOT NULL DEFAULT '',
            region VARCHAR(120) NOT NULL DEFAULT '',
            city VARCHAR(120) NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT '',
            language VARCHAR(80) NOT NULL DEFAULT '',
            timezone VARCHAR(120) NOT NULL DEFAULT '',
            platform VARCHAR(180) NOT NULL DEFAULT '',
            device VARCHAR(80) NOT NULL DEFAULT '',
            screen VARCHAR(80) NOT NULL DEFAULT '',
            viewport VARCHAR(80) NOT NULL DEFAULT '',
            headers_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_landing_events_created ON landing_visit_events(created_at DESC);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_landing_events_source ON landing_visit_events(source, created_at DESC);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_landing_events_visitor ON landing_visit_events(visitor_id, created_at DESC);"))
    await db.execute(text("ALTER TABLE landing_visit_events ADD COLUMN IF NOT EXISTS region VARCHAR(120) NOT NULL DEFAULT '';"))
    await db.execute(text("ALTER TABLE landing_visit_events ADD COLUMN IF NOT EXISTS city VARCHAR(120) NOT NULL DEFAULT '';"))
    await db.commit()


def _admin_required(request: Request) -> None:
    if not _valid_session(request):
        raise HTTPException(status_code=401, detail="admin_v2_session_required")


async def _event_from_request(request: Request) -> LandingEventIn:
    raw = await request.body()
    data: dict[str, Any] = {}
    if raw:
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = {}
    return LandingEventIn.model_validate(data)


async def _store_event(db: AsyncSession, request: Request, event: LandingEventIn) -> None:
    parsed_url = urlparse(event.url or "")
    query = parse_qs(parsed_url.query)
    utm_source = event.utm_source or _first_query_value(query, "utm_source")
    utm_medium = event.utm_medium or _first_query_value(query, "utm_medium")
    utm_campaign = event.utm_campaign or _first_query_value(query, "utm_campaign")
    utm_term = event.utm_term or _first_query_value(query, "utm_term")
    utm_content = event.utm_content or _first_query_value(query, "utm_content")
    normalized = event.model_copy(update={
        "event_type": _clean(event.event_type or "page_view", 80),
        "url": _clean(event.url, 1200),
        "path": _clean(event.path or parsed_url.path or "/", 420),
        "title": _clean(event.title, 260),
        "referrer": _clean(event.referrer, 1200),
        "visitor_id": _clean(event.visitor_id, 120),
        "session_id": _clean(event.session_id, 120),
        "utm_source": _clean(utm_source, 160),
        "utm_medium": _clean(utm_medium, 160),
        "utm_campaign": _clean(utm_campaign, 220),
        "utm_term": _clean(utm_term, 220),
        "utm_content": _clean(utm_content, 220),
        "language": _clean(event.language, 80),
        "timezone": _clean(event.timezone, 120),
        "platform": _clean(event.platform, 160),
        "device": _clean(event.device, 80),
        "screen": _clean(event.screen, 80),
        "viewport": _clean(event.viewport, 80),
    })
    headers = {
        "accept_language": request.headers.get("accept-language", ""),
        "origin": request.headers.get("origin", ""),
        "referer": request.headers.get("referer", ""),
        "country": _country_from_headers(request),
        "region": _region_from_headers(request),
        "city": _city_from_headers(request),
    }
    await db.execute(
        text("""
            INSERT INTO landing_visit_events (
                event_type, landing_url, path, title, referrer, referrer_domain,
                source, medium, campaign, term, content, visitor_id, session_id,
                ip_address, country, region, city, user_agent, language, timezone, platform,
                device, screen, viewport, headers_json, extra_json
            )
            VALUES (
                :event_type, :landing_url, :path, :title, :referrer, :referrer_domain,
                :source, :medium, :campaign, :term, :content, :visitor_id, :session_id,
                :ip_address, :country, :region, :city, :user_agent, :language, :timezone, :platform,
                :device, :screen, :viewport, CAST(:headers_json AS jsonb), CAST(:extra_json AS jsonb)
            )
        """),
        {
            "event_type": normalized.event_type,
            "landing_url": normalized.url,
            "path": normalized.path,
            "title": normalized.title,
            "referrer": normalized.referrer,
            "referrer_domain": _domain(normalized.referrer),
            "source": _source_label(normalized),
            "medium": normalized.utm_medium,
            "campaign": normalized.utm_campaign,
            "term": normalized.utm_term,
            "content": normalized.utm_content,
            "visitor_id": normalized.visitor_id,
            "session_id": normalized.session_id,
            "ip_address": _client_ip(request),
            "country": _country_from_headers(request),
            "region": _region_from_headers(request),
            "city": _city_from_headers(request),
            "user_agent": request.headers.get("user-agent", "")[:1200],
            "language": normalized.language,
            "timezone": normalized.timezone,
            "platform": normalized.platform,
            "device": normalized.device,
            "screen": normalized.screen,
            "viewport": normalized.viewport,
            "headers_json": json.dumps(headers),
            "extra_json": json.dumps(normalized.extra or {}),
        },
    )
    await db.commit()


@router.post("/events", include_in_schema=False)
async def create_landing_event(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await _ensure_storage(db)
    event = await _event_from_request(request)
    await _store_event(db, request, event)
    return {"ok": True, "tracked_at": _now_iso()}


@router.get("/summary")
async def landing_analytics_summary(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=80),
    source: str = Query(default="", max_length=220),
    campaign: str = Query(default="", max_length=260),
    device: str = Query(default="", max_length=80),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _admin_required(request)
    await _ensure_storage(db)
    day_window = int(days)
    row_limit = int(limit)
    filters = {
        "source": _clean(source, 220),
        "campaign": _clean(campaign, 260),
        "device": _clean(device, 80),
    }
    where_parts = [f"created_at >= NOW() - INTERVAL '{day_window} days'"]
    params: dict[str, Any] = {}
    if filters["source"]:
        where_parts.append("source = :source")
        params["source"] = filters["source"]
    if filters["campaign"]:
        where_parts.append("COALESCE(NULLIF(campaign, ''), 'sin campana') = :campaign")
        params["campaign"] = filters["campaign"]
    if filters["device"]:
        where_parts.append("COALESCE(NULLIF(device, ''), 'sin dato') = :device")
        params["device"] = filters["device"]
    where_sql = " AND ".join(where_parts)
    option_where_sql = f"created_at >= NOW() - INTERVAL '{day_window} days'"
    city_expr = """
        COALESCE(
            NULLIF(city, ''),
            NULLIF(INITCAP(REPLACE(SPLIT_PART(timezone, '/', 2), '_', ' ')), ''),
            'Ciudad no detectada'
        )
    """
    country_expr = """
        CASE
            WHEN UPPER(NULLIF(country, '')) = 'CO' THEN 'Colombia'
            WHEN UPPER(NULLIF(country, '')) = 'US' THEN 'Estados Unidos'
            WHEN UPPER(NULLIF(country, '')) = 'MX' THEN 'Mexico'
            WHEN UPPER(NULLIF(country, '')) = 'ES' THEN 'Espana'
            WHEN UPPER(NULLIF(country, '')) = 'AR' THEN 'Argentina'
            WHEN UPPER(NULLIF(country, '')) = 'CL' THEN 'Chile'
            WHEN UPPER(NULLIF(country, '')) = 'PE' THEN 'Peru'
            WHEN UPPER(NULLIF(country, '')) = 'EC' THEN 'Ecuador'
            WHEN UPPER(NULLIF(country, '')) = 'VE' THEN 'Venezuela'
            WHEN UPPER(NULLIF(country, '')) = 'PA' THEN 'Panama'
            WHEN UPPER(NULLIF(country, '')) = 'CR' THEN 'Costa Rica'
            WHEN UPPER(NULLIF(country, '')) = 'DO' THEN 'Republica Dominicana'
            WHEN NULLIF(country, '') IS NOT NULL THEN UPPER(country)
            WHEN timezone = 'America/Bogota' THEN 'Colombia'
            WHEN timezone LIKE 'America/%' THEN 'America'
            WHEN timezone LIKE 'Europe/%' THEN 'Europa'
            ELSE 'Pais no detectado'
        END
    """
    geo_label_expr = f"({city_expr} || ' / ' || {country_expr})"

    row = (await db.execute(text(f"""
        SELECT
            COUNT(*)::int AS total_visits,
            COUNT(DISTINCT NULLIF(visitor_id, ''))::int AS unique_visitors,
            COUNT(DISTINCT NULLIF(session_id, ''))::int AS sessions,
            COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours')::int AS last_24h,
            MIN(created_at)::text AS first_visit_at,
            MAX(created_at)::text AS last_visit_at
        FROM landing_visit_events
        WHERE {where_sql}
    """), params)).mappings().first() or {}

    async def group(sql: str, bind_params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        result = await db.execute(text(sql), bind_params or {})
        return [dict(item) for item in result.mappings().all()]

    sources = await group(f"""
        SELECT source AS label, COUNT(*)::int AS total
        FROM landing_visit_events
        WHERE {where_sql}
        GROUP BY source
        ORDER BY total DESC, label ASC
        LIMIT {row_limit}
    """, params)
    campaigns = await group(f"""
        SELECT COALESCE(NULLIF(campaign, ''), 'sin campana') AS label, COUNT(*)::int AS total
        FROM landing_visit_events
        WHERE {where_sql}
        GROUP BY COALESCE(NULLIF(campaign, ''), 'sin campana')
        ORDER BY total DESC, label ASC
        LIMIT {row_limit}
    """, params)
    paths = await group(f"""
        SELECT path AS label, COUNT(*)::int AS total
        FROM landing_visit_events
        WHERE {where_sql}
        GROUP BY path
        ORDER BY total DESC, label ASC
        LIMIT {row_limit}
    """, params)
    devices = await group(f"""
        SELECT COALESCE(NULLIF(device, ''), 'sin dato') AS label, COUNT(*)::int AS total
        FROM landing_visit_events
        WHERE {where_sql}
        GROUP BY COALESCE(NULLIF(device, ''), 'sin dato')
        ORDER BY total DESC, label ASC
        LIMIT {row_limit}
    """, params)
    geo = await group(f"""
        SELECT {geo_label_expr} AS label, COUNT(*)::int AS total
        FROM landing_visit_events
        WHERE {where_sql}
        GROUP BY {geo_label_expr}
        ORDER BY total DESC, label ASC
        LIMIT {row_limit}
    """, params)
    daily = await group(f"""
        SELECT
            TO_CHAR(created_at AT TIME ZONE 'America/Bogota', 'YYYY-MM-DD') AS label,
            COUNT(*)::int AS total
        FROM landing_visit_events
        WHERE {where_sql}
        GROUP BY TO_CHAR(created_at AT TIME ZONE 'America/Bogota', 'YYYY-MM-DD')
        ORDER BY label ASC
    """, params)
    recent = await group(f"""
        SELECT
            created_at::text AS created_at,
            source,
            medium,
            campaign,
            path,
            referrer_domain,
            country,
            {country_expr} AS country_name,
            region,
            city,
            {city_expr} AS city_name,
            language,
            timezone,
            device,
            viewport
        FROM landing_visit_events
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT {row_limit}
    """, params)
    option_sources = await group(f"""
        SELECT source AS label, COUNT(*)::int AS total
        FROM landing_visit_events
        WHERE {option_where_sql}
        GROUP BY source
        ORDER BY total DESC, label ASC
        LIMIT 80
    """)
    option_campaigns = await group(f"""
        SELECT COALESCE(NULLIF(campaign, ''), 'sin campana') AS label, COUNT(*)::int AS total
        FROM landing_visit_events
        WHERE {option_where_sql}
        GROUP BY COALESCE(NULLIF(campaign, ''), 'sin campana')
        ORDER BY total DESC, label ASC
        LIMIT 80
    """)
    option_devices = await group(f"""
        SELECT COALESCE(NULLIF(device, ''), 'sin dato') AS label, COUNT(*)::int AS total
        FROM landing_visit_events
        WHERE {option_where_sql}
        GROUP BY COALESCE(NULLIF(device, ''), 'sin dato')
        ORDER BY total DESC, label ASC
        LIMIT 80
    """)

    return {
        "ok": True,
        "days": day_window,
        "filters": filters,
        "totals": dict(row),
        "sources": sources,
        "campaigns": campaigns,
        "paths": paths,
        "devices": devices,
        "geo": geo,
        "daily": daily,
        "recent": recent,
        "options": {
            "sources": option_sources,
            "campaigns": option_campaigns,
            "devices": option_devices,
        },
        "tracking_endpoint": LANDING_TRACKING_ENDPOINT,
        "snippet": landing_tracking_snippet(),
    }


def landing_tracking_snippet() -> str:
    return f"""<script>
(function () {{
  var endpoint = "{LANDING_TRACKING_ENDPOINT}";
  var visitorKey = "clonexa_landing_visitor_id";
  var sessionKey = "clonexa_landing_session_id";
  function id(prefix) {{
    return prefix + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }}
  var visitorId = localStorage.getItem(visitorKey);
  if (!visitorId) {{
    visitorId = id("vis");
    localStorage.setItem(visitorKey, visitorId);
  }}
  var sessionId = sessionStorage.getItem(sessionKey);
  if (!sessionId) {{
    sessionId = id("ses");
    sessionStorage.setItem(sessionKey, sessionId);
  }}
  var payload = {{
    event_type: "page_view",
    url: location.href,
    path: location.pathname,
    title: document.title,
    referrer: document.referrer,
    visitor_id: visitorId,
    session_id: sessionId,
    language: navigator.language || "",
    timezone: (Intl.DateTimeFormat().resolvedOptions().timeZone || ""),
    platform: navigator.platform || "",
    device: /Mobi|Android/i.test(navigator.userAgent) ? "mobile" : "desktop",
    screen: screen.width + "x" + screen.height,
    viewport: innerWidth + "x" + innerHeight,
    extra: {{
      userAgent: navigator.userAgent,
      landingTracker: "025R"
    }}
  }};
  var body = JSON.stringify(payload);
  if (!navigator.sendBeacon || !navigator.sendBeacon(endpoint, body)) {{
    fetch(endpoint, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: body,
      keepalive: true
    }}).catch(function () {{}});
  }}
}})();
</script>"""


@router.get("/snippet")
async def landing_analytics_snippet(request: Request) -> dict[str, str]:
    _admin_required(request)
    return {"snippet": landing_tracking_snippet(), "endpoint": LANDING_TRACKING_ENDPOINT}
