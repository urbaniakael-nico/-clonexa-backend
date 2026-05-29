from __future__ import annotations

import hashlib
import inspect
import json
import time
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import get_db

try:
    from app.core.config import get_settings
except Exception:
    get_settings = None


router = APIRouter()

ALLOWED_EVENT_TYPES = {
    "page_view",
    "section_view",
    "assembly_view",
    "video_play",
    "video_complete",
    "cta_click",
    "email_click",
    "demo_request",
}

MAX_METADATA_BYTES = 5000
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_EVENTS = 160
_RATE_BUCKETS: dict[str, list[float]] = {}


class LandingEventIn(BaseModel):
    event_type: str = Field(min_length=2, max_length=80)
    visitor_id: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    path: str | None = Field(default=None, max_length=500)
    section: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=120)
    referrer: str | None = Field(default=None, max_length=1000)
    utm_source: str | None = Field(default=None, max_length=120)
    utm_medium: str | None = Field(default=None, max_length=120)
    utm_campaign: str | None = Field(default=None, max_length=180)
    device_type: str | None = Field(default=None, max_length=80)
    browser: str | None = Field(default=None, max_length=160)
    country: str | None = Field(default=None, max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _execute(db: Any, statement: Any, params: dict[str, Any] | None = None) -> Any:
    return await _maybe_await(db.execute(statement, params or {}))


async def _commit(db: Any) -> None:
    await _maybe_await(db.commit())


def _settings_secret() -> str:
    try:
        if get_settings:
            settings = get_settings()
            return str(
                getattr(settings, "JWT_SECRET_KEY", None)
                or getattr(settings, "SECRET_KEY", None)
                or "clonexa-landing-analytics"
            )
    except Exception:
        pass

    return "clonexa-landing-analytics"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def _ip_hash(request: Request) -> str:
    raw = f"{_settings_secret()}:{_client_ip(request)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _rate_limit(request: Request) -> None:
    key = _ip_hash(request)
    now = time.time()
    bucket = [item for item in _RATE_BUCKETS.get(key, []) if now - item < RATE_LIMIT_WINDOW_SECONDS]

    if len(bucket) >= RATE_LIMIT_MAX_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too_many_landing_events",
        )

    bucket.append(now)
    _RATE_BUCKETS[key] = bucket


def _clean_text(value: Any, max_len: int = 500) -> str | None:
    if value is None:
        return None

    text_value = str(value).strip()

    if not text_value:
        return None

    return text_value[:max_len]


def _clean_metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    safe: dict[str, Any] = {}

    for key, item in value.items():
        k = str(key)[:80]

        if item is None:
            safe[k] = None
        elif isinstance(item, (str, int, float, bool)):
            safe[k] = str(item)[:500] if isinstance(item, str) else item
        elif isinstance(item, (list, tuple)):
            safe[k] = [str(x)[:200] for x in list(item)[:20]]
        elif isinstance(item, dict):
            safe[k] = {str(a)[:80]: str(b)[:200] for a, b in list(item.items())[:20]}
        else:
            safe[k] = str(item)[:300]

    encoded = json.dumps(safe, ensure_ascii=False, default=str)

    if len(encoded.encode("utf-8")) <= MAX_METADATA_BYTES:
        return safe

    return {
        "truncated": True,
        "original_keys": list(safe.keys())[:50],
    }


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, uuid.UUID):
        return str(value)

    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_serialize(v) for v in value]

    return value


def _row_dict(row: Any) -> dict[str, Any]:
    mapping = getattr(row, "_mapping", row)
    return {str(k): _serialize(v) for k, v in dict(mapping).items()}


async def ensure_landing_events_table(db: Any) -> None:
    await _execute(
        db,
        text(
            """
            CREATE TABLE IF NOT EXISTS landing_events (
                id UUID PRIMARY KEY,
                event_type VARCHAR(80) NOT NULL,
                visitor_id VARCHAR(128),
                session_id VARCHAR(128),
                path TEXT,
                section VARCHAR(120),
                source VARCHAR(120),
                referrer TEXT,
                utm_source VARCHAR(120),
                utm_medium VARCHAR(120),
                utm_campaign VARCHAR(180),
                device_type VARCHAR(80),
                browser VARCHAR(160),
                country VARCHAR(80),
                origin TEXT,
                user_agent TEXT,
                ip_hash VARCHAR(128),
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        ),
    )

    await _execute(db, text("CREATE INDEX IF NOT EXISTS ix_landing_events_created_at ON landing_events (created_at DESC)"))
    await _execute(db, text("CREATE INDEX IF NOT EXISTS ix_landing_events_type_created_at ON landing_events (event_type, created_at DESC)"))
    await _execute(db, text("CREATE INDEX IF NOT EXISTS ix_landing_events_visitor ON landing_events (visitor_id)"))
    await _execute(db, text("CREATE INDEX IF NOT EXISTS ix_landing_events_session ON landing_events (session_id)"))

    await _commit(db)


@router.post("/public/landing/events")
async def collect_landing_event(
    payload: LandingEventIn,
    request: Request,
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    _rate_limit(request)

    event_type = _clean_text(payload.event_type, 80)

    if event_type not in ALLOWED_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_event_type",
        )

    await ensure_landing_events_table(db)

    origin = _clean_text(request.headers.get("origin"), 1000)
    user_agent = _clean_text(request.headers.get("user-agent"), 1000)
    metadata = _clean_metadata(payload.metadata)

    event_id = uuid.uuid4()

    await _execute(
        db,
        text(
            """
            INSERT INTO landing_events (
                id,
                event_type,
                visitor_id,
                session_id,
                path,
                section,
                source,
                referrer,
                utm_source,
                utm_medium,
                utm_campaign,
                device_type,
                browser,
                country,
                origin,
                user_agent,
                ip_hash,
                metadata,
                created_at
            )
            VALUES (
                :id,
                :event_type,
                :visitor_id,
                :session_id,
                :path,
                :section,
                :source,
                :referrer,
                :utm_source,
                :utm_medium,
                :utm_campaign,
                :device_type,
                :browser,
                :country,
                :origin,
                :user_agent,
                :ip_hash,
                CAST(:metadata AS JSONB),
                now()
            )
            """
        ),
        {
            "id": str(event_id),
            "event_type": event_type,
            "visitor_id": _clean_text(payload.visitor_id, 128),
            "session_id": _clean_text(payload.session_id, 128),
            "path": _clean_text(payload.path, 500),
            "section": _clean_text(payload.section, 120),
            "source": _clean_text(payload.source, 120),
            "referrer": _clean_text(payload.referrer, 1000),
            "utm_source": _clean_text(payload.utm_source, 120),
            "utm_medium": _clean_text(payload.utm_medium, 120),
            "utm_campaign": _clean_text(payload.utm_campaign, 180),
            "device_type": _clean_text(payload.device_type, 80),
            "browser": _clean_text(payload.browser, 160),
            "country": _clean_text(payload.country, 80),
            "origin": origin,
            "user_agent": user_agent,
            "ip_hash": _ip_hash(request),
            "metadata": json.dumps(metadata, ensure_ascii=False, default=str),
        },
    )

    await _commit(db)

    return {
        "ok": True,
        "event_id": str(event_id),
        "event_type": event_type,
    }


@router.get("/admin/analytics/landing/summary")
async def landing_analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    await ensure_landing_events_table(db)

    result = await _execute(
        db,
        text(
            """
            SELECT
                COUNT(*)::int AS total_events,
                COUNT(*) FILTER (WHERE event_type = 'page_view')::int AS page_views,
                COUNT(DISTINCT NULLIF(visitor_id, ''))::int AS unique_visitors,
                COUNT(DISTINCT NULLIF(session_id, ''))::int AS unique_sessions,
                COUNT(*) FILTER (WHERE event_type IN ('cta_click', 'demo_request'))::int AS cta_clicks,
                COUNT(*) FILTER (WHERE event_type = 'email_click')::int AS email_clicks,
                COUNT(*) FILTER (WHERE event_type = 'video_play')::int AS video_plays,
                COUNT(*) FILTER (WHERE event_type = 'video_complete')::int AS video_completes,
                COUNT(*) FILTER (WHERE event_type = 'assembly_view')::int AS assembly_views,
                MIN(created_at) AS first_event_at,
                MAX(created_at) AS last_event_at
            FROM landing_events
            WHERE created_at >= now() - make_interval(days => CAST(:days AS integer))
            """
        ),
        {"days": days},
    )

    summary = _row_dict(result.first() or {})

    sources_result = await _execute(
        db,
        text(
            """
            SELECT
                COALESCE(NULLIF(source, ''), 'direct') AS source,
                COUNT(*)::int AS count
            FROM landing_events
            WHERE created_at >= now() - make_interval(days => CAST(:days AS integer))
            GROUP BY 1
            ORDER BY count DESC
            LIMIT 8
            """
        ),
        {"days": days},
    )

    sections_result = await _execute(
        db,
        text(
            """
            SELECT
                COALESCE(NULLIF(section, ''), 'landing') AS section,
                COUNT(*)::int AS count
            FROM landing_events
            WHERE created_at >= now() - make_interval(days => CAST(:days AS integer))
              AND event_type IN ('section_view', 'assembly_view')
            GROUP BY 1
            ORDER BY count DESC
            LIMIT 10
            """
        ),
        {"days": days},
    )

    devices_result = await _execute(
        db,
        text(
            """
            SELECT
                COALESCE(NULLIF(device_type, ''), 'unknown') AS device_type,
                COUNT(*)::int AS count
            FROM landing_events
            WHERE created_at >= now() - make_interval(days => CAST(:days AS integer))
            GROUP BY 1
            ORDER BY count DESC
            LIMIT 8
            """
        ),
        {"days": days},
    )

    unique_visitors = int(summary.get("unique_visitors") or 0)
    cta_clicks = int(summary.get("cta_clicks") or 0)

    summary["conversion_rate"] = round((cta_clicks / unique_visitors) * 100, 2) if unique_visitors else 0
    summary["days"] = days
    summary["top_sources"] = [_row_dict(row) for row in sources_result.fetchall()]
    summary["top_sections"] = [_row_dict(row) for row in sections_result.fetchall()]
    summary["devices"] = [_row_dict(row) for row in devices_result.fetchall()]

    return summary


@router.get("/admin/analytics/landing/daily")
async def landing_analytics_daily(
    days: int = Query(default=14, ge=1, le=365),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    await ensure_landing_events_table(db)

    result = await _execute(
        db,
        text(
            """
            SELECT
                date_trunc('day', created_at)::date AS day,
                COUNT(*) FILTER (WHERE event_type = 'page_view')::int AS page_views,
                COUNT(DISTINCT NULLIF(visitor_id, ''))::int AS unique_visitors,
                COUNT(*) FILTER (WHERE event_type IN ('cta_click', 'demo_request'))::int AS cta_clicks,
                COUNT(*) FILTER (WHERE event_type = 'video_play')::int AS video_plays,
                COUNT(*) FILTER (WHERE event_type = 'assembly_view')::int AS assembly_views
            FROM landing_events
            WHERE created_at >= now() - make_interval(days => CAST(:days AS integer))
            GROUP BY 1
            ORDER BY 1 ASC
            """
        ),
        {"days": days},
    )

    return {
        "days": days,
        "items": [_row_dict(row) for row in result.fetchall()],
    }


@router.get("/admin/analytics/landing/events")
async def landing_analytics_events(
    limit: int = Query(default=80, ge=1, le=500),
    event_type: str | None = Query(default=None, max_length=80),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    await ensure_landing_events_table(db)

    params: dict[str, Any] = {"limit": limit}
    where = ""

    if event_type:
        where = "WHERE event_type = :event_type"
        params["event_type"] = event_type

    result = await _execute(
        db,
        text(
            f"""
            SELECT
                id,
                event_type,
                visitor_id,
                session_id,
                path,
                section,
                source,
                referrer,
                utm_source,
                utm_medium,
                utm_campaign,
                device_type,
                browser,
                country,
                origin,
                metadata,
                created_at
            FROM landing_events
            {where}
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        params,
    )

    return {
        "items": [_row_dict(row) for row in result.fetchall()],
    }