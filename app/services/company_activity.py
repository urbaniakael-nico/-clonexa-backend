"""Actividad de UNA empresa para la Ficha de la Consola v2+ (solo lectura).

- Ingresos por dia de los ultimos 14 dias: sesiones creadas en
  clonexa_access_sessions, agrupadas por dia en America/Bogota.
- Resumen de sesiones: abiertas con actividad en las ultimas 24 h, abiertas
  "sin actividad" (mas viejas: nadie las cerro), conectadas ahora (15 min) y
  la ultima actividad.
- Usuarios por tipo de mini panel (company_users con settings_json.mini_panel
  encendido), la misma regla que GET /companies/{id}/mini-panel-users.
Todas las consultas filtran por company_id. Una tabla que no existe cuenta
como vacia.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BOGOTA = ZoneInfo("America/Bogota")
DAYS = 14
RECENT_HOURS = 24
CONNECTED_MINUTES = 15


def _iso(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


async def _exists(db: AsyncSession, table: str) -> bool:
    return bool((await db.execute(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": f"public.{table}"})).scalar())


async def company_activity(db: AsyncSession, company_id: str, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(BOGOTA).date()
    first = today - timedelta(days=DAYS - 1)
    since = datetime.combine(first, time.min, BOGOTA).astimezone(timezone.utc)
    by_day = {first + timedelta(days=i): 0 for i in range(DAYS)}
    sessions = {"open": 0, "open_recent": 0, "stale": 0, "connected_now": 0, "users_connected": 0,
                "last_seen_at": None, "recent_hours": RECENT_HOURS}
    params = {"cid": str(company_id)}

    if await _exists(db, "clonexa_access_sessions"):
        for r in (await db.execute(text("""
            SELECT (created_at AT TIME ZONE 'America/Bogota')::date AS day, COUNT(*) AS logins
            FROM clonexa_access_sessions
            WHERE company_id = CAST(:cid AS uuid) AND created_at >= :since
            GROUP BY 1
        """), {**params, "since": since})).mappings().all():
            if r["day"] in by_day:
                by_day[r["day"]] = int(r["logins"] or 0)
        row = (await db.execute(text("""
            SELECT COUNT(*) FILTER (WHERE status = 'active') AS open,
                   COUNT(*) FILTER (WHERE status = 'active' AND last_seen_at >= :recent) AS open_recent,
                   COUNT(*) FILTER (WHERE status = 'active' AND last_seen_at >= :live) AS connected,
                   COUNT(DISTINCT COALESCE(subject_id::text, session_key))
                     FILTER (WHERE status = 'active' AND last_seen_at >= :live) AS users_connected,
                   MAX(last_seen_at) AS last_seen
            FROM clonexa_access_sessions
            WHERE company_id = CAST(:cid AS uuid)
        """), {**params, "recent": now - timedelta(hours=RECENT_HOURS),
               "live": now - timedelta(minutes=CONNECTED_MINUTES)})).mappings().first() or {}
        open_total = int(row.get("open") or 0)
        recent = int(row.get("open_recent") or 0)
        sessions.update(open=open_total, open_recent=recent, stale=max(0, open_total - recent),
                        connected_now=int(row.get("connected") or 0),
                        users_connected=int(row.get("users_connected") or 0), last_seen_at=_iso(row.get("last_seen")))

    panels: dict[str, dict[str, int]] = {}
    if await _exists(db, "company_users"):
        for r in (await db.execute(text("""
            SELECT settings_json->'mini_panel'->>'type' AS panel_type,
                   COUNT(*) AS users,
                   COUNT(*) FILTER (WHERE LOWER(COALESCE(status, '')) IN ('active', 'activo')) AS active
            FROM company_users
            WHERE company_id = CAST(:cid AS uuid)
              AND jsonb_typeof(settings_json->'mini_panel') = 'object'
              AND settings_json->'mini_panel'->'enabled' = 'true'::jsonb
            GROUP BY 1
        """), params)).mappings().all():
            panel = str(r["panel_type"] or "").strip().lower()
            if panel:
                panels[panel] = {"users": int(r["users"] or 0), "active": int(r["active"] or 0)}

    return {
        "ok": True,
        "company_id": str(company_id),
        "timezone": "America/Bogota",
        "days": [{"date": day.isoformat(), "logins": count} for day, count in by_day.items()],
        "sessions": sessions,
        "panels": panels,
        "generated_at": now.isoformat(),
    }
