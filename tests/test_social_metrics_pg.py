"""Redes sociales de Nexa contra Postgres REAL (pgserver) y la app completa.

- POST /api/v1/social-metrics/ingest: limite, variable (503), token (401),
  upsert idempotente, null no borra, red invalida y mas de 200 elementos 422.
- GET /api/v1/social-metrics/summary: solo Admin V2; embudo con visitas por
  utm_source y por referrer; visitas por red y por campana nexa-*.
"""
from __future__ import annotations

import asyncio
import importlib
import tempfile
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

pgserver = pytest.importorskip("pgserver")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.main as app_main  # noqa: E402
from app.api.deps import get_db  # noqa: E402
from app.api.v1.endpoints import landing_analytics  # noqa: E402
from app.api.v1.endpoints import social_metrics as sm  # noqa: E402
from app.web import admin_v2_routes  # noqa: E402

TOKEN = "prueba-" + "x" * 40
URL = "/api/v1/social-metrics"


def _migration() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module("migrations.versions.024r_social_metrics")
    module.op = Op()
    module.upgrade()
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_social_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            for stmt in _migration():
                await conn.execute(text(stmt))
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as db:
            await landing_analytics._ensure_storage(db)  # la tabla de hoy, tal cual
        await engine.dispose()

    asyncio.run(setup())
    yield url


def _run(url: str, sql: str, params: dict | None = None, fetch: bool = True):
    async def go():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), params or {})
            rows = [dict(r) for r in result.mappings().all()] if fetch else None
        await engine.dispose()
        return rows
    return asyncio.run(go())


@pytest.fixture
def client(pg_url, monkeypatch):
    _run(pg_url, "TRUNCATE social_daily_metrics, social_posts, landing_visit_events", fetch=False)

    async def db_dep():
        engine = create_async_engine(pg_url, poolclass=NullPool)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            yield session
        await engine.dispose()

    monkeypatch.setenv(sm.TOKEN_ENV, TOKEN)
    sm.INGEST_PER_IP.hits.clear()
    app_main.app.dependency_overrides[get_db] = db_dep
    yield TestClient(app_main.app)
    app_main.app.dependency_overrides.pop(get_db, None)


def _post(c, body, token=TOKEN):
    headers = {"X-Nexa-Token": token} if token is not None else {}
    return c.post(f"{URL}/ingest", json=body, headers=headers)


def _admin(monkeypatch, ok=True):
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=ok))


# ------------------------------------------------------------------ ingest
def test_sin_token_401_y_token_malo_401(client):
    assert _post(client, {}, token=None).status_code == 401
    assert _post(client, {}, token="otro").status_code == 401
    r = _post(client, {"snapshots": [{"network": "nope"}]}, token=None)
    assert r.status_code == 401, "sin token no se valida el cuerpo"
    assert TOKEN not in r.text


def test_sin_variable_503(client, monkeypatch):
    monkeypatch.delenv(sm.TOKEN_ENV, raising=False)
    assert _post(client, {}).status_code == 503
    monkeypatch.setenv(sm.TOKEN_ENV, "   ")
    assert _post(client, {}).status_code == 503


def test_limite_60_por_minuto_por_ip(client):
    for _ in range(60):
        assert _post(client, {}).status_code == 200
    assert _post(client, {}).status_code == 429


def test_upsert_idempotente_y_null_no_borra(client, pg_url):
    today = sm._today().isoformat()
    body = {
        "snapshots": [{"network": "Instagram", "metric_date": today, "followers": 120, "views": 900, "engagements": 40, "raw": {"a": 1}}],
        "posts": [{"network": "youtube", "external_id": "yt-1", "url": "https://youtu.be/x", "published_at": f"{today}T10:00:00-05:00",
                   "tema": "Inventario", "caption": "c" * 900, "utm_campaign": "nexa-2026-s43", "views": 300, "likes": 12}],
    }
    for _ in range(2):
        r = _post(client, body)
        assert r.status_code == 200 and r.json() == {"ok": True, "snapshots": 1, "posts": 1}
    assert _run(pg_url, "SELECT COUNT(*) AS n FROM social_daily_metrics")[0]["n"] == 1
    assert _run(pg_url, "SELECT COUNT(*) AS n FROM social_posts")[0]["n"] == 1

    later = {"snapshots": [{"network": "instagram", "metric_date": today, "followers": None, "views": 950}],
             "posts": [{"network": "youtube", "external_id": "yt-1", "views": 410, "likes": None, "tema": None}]}
    assert _post(client, later).status_code == 200
    snap = _run(pg_url, "SELECT followers, views, engagements, raw FROM social_daily_metrics")[0]
    assert (snap["followers"], snap["views"], snap["engagements"], snap["raw"]) == (120, 950, 40, {"a": 1})
    post = _run(pg_url, "SELECT views, likes, tema, utm_campaign, length(caption) AS cap, url FROM social_posts")[0]
    assert (post["views"], post["likes"], post["tema"], post["utm_campaign"], post["cap"], post["url"]) == (410, 12, "Inventario", "nexa-2026-s43", 600, "https://youtu.be/x")


def test_red_invalida_y_mas_de_200_son_422(client, pg_url):
    today = sm._today().isoformat()
    assert _post(client, {"snapshots": [{"network": "myspace", "metric_date": today}]}).status_code == 422
    assert _post(client, {"posts": [{"network": "x", "external_id": "1"}]}).status_code == 422
    many = [{"network": "facebook", "metric_date": (sm._today() - timedelta(days=i)).isoformat()} for i in range(201)]
    assert _post(client, {"snapshots": many}).status_code == 422
    posts = [{"network": "facebook", "external_id": str(i)} for i in range(201)]
    assert _post(client, {"posts": posts}).status_code == 422
    assert _post(client, {"snapshots": many[:200]}).status_code == 200, "200 justos pasan"
    assert _post(client, {"snapshots": [{"network": "facebook", "metric_date": today, "views": -1}]}).status_code == 422
    assert _run(pg_url, "SELECT COUNT(*) AS n FROM social_daily_metrics")[0]["n"] == 200


def test_raw_gigante_no_se_guarda(client, pg_url):
    today = sm._today().isoformat()
    assert _post(client, {"snapshots": [{"network": "linkedin", "metric_date": today, "raw": {"x": "y" * 20000}}]}).status_code == 200
    raw = _run(pg_url, "SELECT raw FROM social_daily_metrics")[0]["raw"]
    assert set(raw) == {"_omitido"}


# ------------------------------------------------------------------ summary
def test_summary_exige_sesion_admin_v2(client, monkeypatch):
    _admin(monkeypatch, ok=False)
    assert client.get(f"{URL}/summary").status_code == 401
    _admin(monkeypatch)
    assert client.get(f"{URL}/summary?days=14").status_code == 422
    assert client.get(f"{URL}/summary?days=7").status_code == 200


def _visit(url, source, referrer_domain, visitor, campaign="", ago_days=0):
    _run(url, """INSERT INTO landing_visit_events (source, referrer_domain, visitor_id, campaign, created_at)
                 VALUES (:s, :r, :v, :c, NOW() - make_interval(days => :d))""",
         {"s": source, "r": referrer_domain, "v": visitor, "c": campaign, "d": ago_days}, fetch=False)


def test_summary_embudo_redes_y_campanas(client, pg_url, monkeypatch):
    _admin(monkeypatch)
    today = sm._today()
    _post(client, {"snapshots": [
        {"network": "instagram", "metric_date": (today - timedelta(days=40)).isoformat(), "followers": 100},
        {"network": "instagram", "metric_date": (today - timedelta(days=3)).isoformat(), "followers": 130, "views": 500, "engagements": 20},
        {"network": "instagram", "metric_date": today.isoformat(), "followers": 150, "views": 700, "engagements": 30},
        {"network": "facebook", "metric_date": today.isoformat(), "followers": 80, "views": 300},
    ], "posts": [
        {"network": "instagram", "external_id": "ig-1", "published_at": f"{today.isoformat()}T09:00:00-05:00", "tema": "Turnos", "views": 400, "likes": 9, "comments": 2, "shares": 1, "url": "https://instagram.com/p/1"},
        {"network": "youtube", "external_id": "yt-1", "published_at": f"{(today - timedelta(days=2)).isoformat()}T09:00:00-05:00", "tema": "Caja", "views": 250, "likes": 5},
        {"network": "youtube", "external_id": "yt-viejo", "published_at": f"{(today - timedelta(days=60)).isoformat()}T09:00:00-05:00", "views": 999},
    ]})
    _visit(pg_url, "instagram", "", "v1", "nexa-2026-s43")
    _visit(pg_url, "instagram", "", "v1", "nexa-2026-s43")
    _visit(pg_url, "m.facebook.com", "m.facebook.com", "v2")        # sin utm: referrer
    _visit(pg_url, "www.facebook.com", "www.facebook.com", "v3")
    _visit(pg_url, "google", "l.instagram.com", "v4", "nexa-2026-s42")  # utm de otra fuente, referrer de red
    _visit(pg_url, "lnkd.in", "lnkd.in", "v5")
    _visit(pg_url, "directo", "", "v6")
    _visit(pg_url, "google.com", "google.com", "v7", "octubre")
    _visit(pg_url, "youtube", "", "v8", ago_days=45)                 # fuera del periodo

    data = client.get(f"{URL}/summary?days=30").json()
    nets = {n["network"]: n for n in data["networks"]}
    assert [n["network"] for n in data["networks"]] == list(sm.NETWORKS)
    ig = nets["instagram"]
    assert (ig["followers"], ig["followers_change"], ig["views"], ig["engagements"], ig["posts"]) == (150, 50, 1200, 50, 1)
    assert len(ig["series"]) == 30 and ig["series"][-1] == {"date": today.isoformat(), "followers": 150, "views": 700}
    assert nets["youtube"]["views"] == 250 and nets["youtube"]["posts"] == 1, "sin cifras diarias usa las publicaciones del periodo"
    assert nets["tiktok"]["has_data"] is False and nets["tiktok"]["followers"] is None
    assert nets["facebook"]["followers_change"] == 0

    assert [p["tema"] for p in data["posts"]] == ["Turnos", "Caja"], "mas recientes primero y solo del periodo"
    assert data["posts"][0]["label"] == "Instagram" and data["posts"][0]["url"] == "https://instagram.com/p/1"

    assert data["funnel"] == {"social_views": 1200 + 300 + 250, "landing_visits": 6, "unique_visitors": 5}
    by = {r["network"]: (r["visits"], r["unique_visitors"]) for r in data["landing_by_network"]}
    assert by == {"instagram": (3, 2), "facebook": (2, 2), "linkedin": (1, 1)}
    camps = {r["campaign"]: r["visits"] for r in data["landing_by_campaign"]}
    assert camps == {"nexa-2026-s43": 2, "nexa-2026-s42": 1}


def test_summary_sin_datos_y_sin_tabla_de_landing(client, pg_url, monkeypatch):
    _admin(monkeypatch)
    data = client.get(f"{URL}/summary").json()
    assert data["funnel"] == {"social_views": 0, "landing_visits": 0, "unique_visitors": 0}
    assert all(n["has_data"] is False for n in data["networks"])
    assert data["posts"] == [] and data["landing_by_campaign"] == []


# ------------------------------------------------------------------ criterio de red
CASES = [
    ("instagram", "", "instagram"), ("Facebook", "", "facebook"), ("google", "l.instagram.com", "instagram"),
    ("m.facebook.com", "m.facebook.com", "facebook"), ("www.facebook.com", "", "facebook"), ("l.facebook.com", "", "facebook"),
    ("youtu.be", "", "youtube"), ("www.youtube.com", "www.youtube.com", "youtube"), ("lnkd.in", "", "linkedin"),
    ("www.linkedin.com", "", "linkedin"), ("www.tiktok.com", "", "tiktok"), ("directo", "", None), ("google.com", "google.com", None),
    ("notinstagram.com", "", None), ("instagram.com.evil.co", "", None),
]


@pytest.mark.parametrize("source,referrer,expected", CASES)
def test_network_of(source, referrer, expected):
    assert sm.network_of(source, referrer) == expected


def test_el_sql_usa_el_mismo_criterio(pg_url):
    values = ", ".join(f"('{s}', '{r}', {i})" for i, (s, r, _) in enumerate(CASES))
    rows = _run(pg_url, f"SELECT i, {sm.network_case_sql()} AS network FROM (VALUES {values}) AS t(source, referrer_domain, i) ORDER BY i")
    assert [r["network"] for r in rows] == [e for _, _, e in CASES]


def test_las_rutas_tienen_guarda_visible():
    from fastapi.routing import APIRoute
    from app.services import console_catalog as cc

    by_path = {r.path: r for r in app_main.app.routes if isinstance(r, APIRoute)}
    assert cc._route_has_auth(by_path["/api/v1/social-metrics/ingest"])
    assert cc._route_has_auth(by_path["/api/v1/social-metrics/summary"])
