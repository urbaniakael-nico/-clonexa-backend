"""Prospeccion de Nexa contra Postgres REAL (pgserver) y la app completa.

- Migracion 025i idempotente (dos veces) y semillas: 6 zonas de Kennedy/Techo/Hipotecho y cadenas.
- Autenticacion: n8n sin token 401 / sin variable 503; consola sin sesion 401; baja con token malo 404.
- Prospeccion de prueba en Kennedy con 20 negocios: sin cadenas, sin duplicados, solo abiertos, en la
  zona, correo solo de la web (y de donde salio).
- Lote: nada sale sin aprobar; horario legal; espaciado; 1 contacto por semana; seguimiento unico a
  los 7 dias; baja por enlace bloquea todo; respuesta NO = baja; respuesta = respondio.
- Landing: visita con utm de un prospecto -> "abrio"; visita normal -> ciudad aproximada y IP recortada.
- WhatsApp: mensaje con el codigo -> se liga, consentimiento, y el reenvio a n8n lleva el prospecto.
- Mapa: tarjetas, zonas con puntaje, correo oculto en los pines y completo solo en la ficha.
"""
from __future__ import annotations

import asyncio
import importlib
import tempfile
import time
from datetime import datetime, timedelta, timezone
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
from app.api.v1.endpoints import prospecting as ep  # noqa: E402
from app.services import ip_geo  # noqa: E402
from app.services import nexa_whatsapp as nw  # noqa: E402
from app.services import prospecting as ps  # noqa: E402
from app.web import admin_v2_routes  # noqa: E402

TOKEN = "prueba-" + "p" * 40
URL = "/api/v1/prospecting"
H = {"X-Nexa-Token": TOKEN}
BOG = ps.BOGOTA


def _statements(name: str) -> list[str]:
    out: list[str] = []

    class Op:
        def execute(self, sql):
            out.append(str(sql))

    module = importlib.import_module(f"migrations.versions.{name}")
    module.op = Op()
    module.upgrade()
    return out


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_prosp_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url, poolclass=NullPool)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as db:
            await landing_analytics._ensure_storage(db)  # la tabla de hoy, como en produccion
        async with engine.begin() as conn:
            for stmt in _statements("024w_nexa_whatsapp"):
                await conn.execute(text(stmt))
            for _ in range(2):  # idempotente
                for stmt in _statements("025i_prospecting"):
                    await conn.execute(text(stmt))
            for _ in range(2):  # idempotente
                for stmt in _statements("025p_prospect_multicanal"):
                    await conn.execute(text(stmt))
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


def _with_db(url, fn):
    async def go():
        engine = create_async_engine(url, poolclass=NullPool)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as db:
            out = await fn(db)
        await engine.dispose()
        return out
    return asyncio.run(go())


PAGES = {
    "https://laespiga.com.co/": '<a href="/contacto">Contacto</a>',
    "https://laespiga.com.co/contacto": "<p>pedidos@laespiga.com.co · juan.perez1987@gmail.com</p>",
    "https://sabordecasa.co/": "<p>Escríbenos a <a href='mailto:info@sabordecasa.co'>info@sabordecasa.co</a></p>",
    "https://doncarlos.com/": "<p>Llámanos al 300 000 0000</p>",
}


async def fake_fetch(url):
    return url, PAGES.get(url, "")


@pytest.fixture
def client(pg_url, monkeypatch):
    _run(pg_url, """TRUNCATE prospect_contacts, prospect_batches, prospect_exclusions, prospect_zone_scans, prospects,
                    landing_visit_events, wa_messages, wa_contacts, prospect_api_usage""", fetch=False)
    _run(pg_url, "UPDATE prospect_settings SET config = '{}'::jsonb", fetch=False)

    async def db_dep():
        engine = create_async_engine(pg_url, poolclass=NullPool)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            yield session
        await engine.dispose()

    monkeypatch.setenv(ep.TOKEN_ENV, TOKEN)
    monkeypatch.setattr(ps, "fetch_page", fake_fetch)
    ep.N8N_PER_IP.hits.clear()
    ep.PUBLIC_PER_IP.hits.clear()
    app_main.app.dependency_overrides[get_db] = db_dep
    yield TestClient(app_main.app)
    app_main.app.dependency_overrides.pop(get_db, None)


def _admin(monkeypatch, ok=True):
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=ok))


def _zone(pg_url, slug="kennedy-central"):
    return _run(pg_url, "SELECT * FROM prospect_zones WHERE slug = :s", {"s": slug})[0]


def _place(i, name, *, lat=4.6220, lng=-74.1530, web="", status="OPERATIONAL", primary="restaurant", reviews=25, hours=True):
    p = {"id": f"place-{i}", "displayName": {"text": name}, "formattedAddress": f"Cl. {i} Sur, Bogotá",
         "location": {"latitude": lat, "longitude": lng}, "types": [primary, "food"], "primaryType": primary,
         "businessStatus": status, "nationalPhoneNumber": "601 000 0000", "websiteUri": web,
         "addressComponents": [{"types": ["neighborhood"], "longText": "Kennedy Central"}], "userRatingCount": reviews}
    if hours:
        p["regularOpeningHours"] = {"weekdayDescriptions": ["lunes: 8:00–18:00"]}
    return p


def _kennedy_20():
    places = [_place(i, f"Restaurante Doña Rosa {i}") for i in range(14)]
    places[0]["websiteUri"] = "https://laespiga.com.co/"
    places[0]["displayName"]["text"] = "Panadería La Espiga"
    places[0]["primaryType"] = "bakery"
    places[1]["websiteUri"] = "https://sabordecasa.co/"
    places[2]["websiteUri"] = "https://doncarlos.com/"
    places[3]["websiteUri"] = "https://www.instagram.com/rosa3"
    places += [_place(20, "Frisby Kennedy"), _place(21, "Hamburguesas El Corral Plaza"), _place(22, "KFC Kennedy"),
               _place(23, "Restaurante Cerrado", status="CLOSED_PERMANENTLY"),
               _place(24, "Muy lejos", lat=4.70, lng=-74.05), _place(0, "Panadería La Espiga")]  # 6 que no entran
    return places


def _ingest(c, pg_url, places, **kw):
    z = _zone(pg_url)
    return c.post(f"{URL}/n8n/places", headers=H, json={"zone_id": z["id"], "business_type": "restaurante", "places": places, **kw})


def _at(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=BOG)


# ------------------------------------------------------------------ migracion y autenticacion
def test_semillas_de_zonas_y_cadenas(pg_url):
    zs = _run(pg_url, "SELECT slug, group_name, niches FROM prospect_zones ORDER BY sort")
    assert [z["slug"] for z in zs[:6]] == ["kennedy-central", "castilla", "americas", "timiza", "techo", "hipotecho"]
    assert {z["group_name"] for z in zs[:6]} == {"Kennedy", "Techo", "Hipotecho"} and all(z["niches"] == [] for z in zs[:6])
    bog = zs[6:]
    assert len(bog) == 19 and {z["group_name"] for z in bog} == {"Bogotá"}, "las 19 localidades de Bogotá"
    assert all({"taller", "campo"} <= set(z["niches"]) and "restaurante" not in z["niches"] for z in bog)
    names = {r["name"] for r in _run(pg_url, "SELECT name FROM prospect_chains")}
    assert {"El Corral", "Frisby", "KFC", "McDonald's", "Crepes & Waffles", "Juan Valdez", "Presto", "Subway", "Domino's"} <= names
    cols = {r["column_name"] for r in _run(pg_url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'landing_visit_events'")}
    assert {"ip_hash", "lat", "lng", "geo_source", "prospect_id"} <= cols


def test_revision_id_corto():
    mod = importlib.import_module("migrations.versions.025i_prospecting")
    assert len(mod.revision) <= 32 and mod.down_revision == "025h_wa_group_reports"
    mod = importlib.import_module("migrations.versions.025p_prospect_multicanal")
    assert len(mod.revision) <= 32 and mod.down_revision == "025o_live3d"


N8N_ROUTES = [("get", "/n8n/scan-plan"), ("post", "/n8n/places"), ("get", "/n8n/scan-report"), ("get", "/n8n/refresh-due"),
              ("post", "/n8n/refresh"), ("post", "/n8n/batch/today"), ("post", "/n8n/batch/1/decide"), ("post", "/n8n/outbox/claim"),
              ("post", "/n8n/outbox/1/sent"), ("post", "/n8n/outbox/1/failed"), ("post", "/n8n/test-emails"), ("post", "/n8n/inbound-email")]
ADMIN_ROUTES = [("get", "/admin/map"), ("get", "/admin/prospects/00000000-0000-0000-0000-000000000000"),
                ("post", "/admin/prospects/00000000-0000-0000-0000-000000000000/status"), ("get", "/admin/zones"),
                ("post", "/admin/zones"), ("put", "/admin/zones/1"), ("get", "/admin/chains"), ("put", "/admin/chains"),
                ("get", "/admin/settings"), ("put", "/admin/settings")]


@pytest.mark.parametrize("method,path", N8N_ROUTES)
def test_n8n_sin_token_401_y_sin_variable_503(client, monkeypatch, method, path):
    assert client.request(method.upper(), URL + path, json={}).status_code == 401
    assert client.request(method.upper(), URL + path, json={}, headers={"X-Nexa-Token": "otro"}).status_code == 401
    monkeypatch.delenv(ep.TOKEN_ENV)
    assert client.request(method.upper(), URL + path, json={}, headers=H).status_code == 503


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_consola_sin_sesion_401(client, monkeypatch, method, path):
    _admin(monkeypatch, ok=False)
    r = client.request(method.upper(), URL + path, json={}, headers=H)  # el token de n8n NO abre la consola
    assert r.status_code == 401


def test_baja_con_token_malo_404_y_vista_previa_404(client):
    assert client.get(f"{URL}/baja?t=nada").status_code == 404
    assert client.get(f"{URL}/baja").status_code == 404
    assert client.get(f"{URL}/vista-previa/1?t=nada").status_code == 404


# ------------------------------------------------------------------ prospeccion de prueba en Kennedy
def test_kennedy_20_negocios_sin_cadenas_sin_duplicados_correo_solo_de_la_web(client, pg_url):
    r = _ingest(client, pg_url, _kennedy_20())
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["found"] == 20 and out["new"] == 14 and out["chain"] == 3 and out["closed"] == 1 and out["outside"] == 1
    assert out["duplicate"] == 1 and out["with_email"] == 2
    again = _ingest(client, pg_url, _kennedy_20()).json()
    assert again["new"] == 0 and again["duplicate"] == 15, "sin duplicados por place_id"
    rows = {r["name"]: r for r in _run(pg_url, "SELECT * FROM prospects")}
    assert len(rows) == 14 and not any(n.startswith(("Frisby", "Hamburguesas El Corral", "KFC")) for n in rows)
    espiga = rows["Panadería La Espiga"]
    assert espiga["business_type"] == "panaderia" and espiga["email"] == "pedidos@laespiga.com.co"
    assert espiga["email_source_url"] == "https://laespiga.com.co/contacto", "se guarda de donde salio"
    assert rows["Restaurante Doña Rosa 1"]["email"] == "info@sabordecasa.co"
    assert rows["Restaurante Doña Rosa 2"]["email"] == "" and rows["Restaurante Doña Rosa 2"]["email_status"] == "sin_correo"
    assert rows["Restaurante Doña Rosa 3"]["email_status"] == "sin_web", "Instagram no es web propia"
    assert rows["Restaurante Doña Rosa 5"]["email_status"] == "sin_web"
    assert len({r["code"] for r in rows.values()}) == 14 and all(len(r["unsub_token"]) >= 30 for r in rows.values())
    scans = _run(pg_url, "SELECT * FROM prospect_zone_scans")
    assert len(scans) == 1 and scans[0]["last_new"] == 0  # la segunda pasada no trajo nuevos
    rep = client.get(f"{URL}/n8n/scan-report", headers=H).json()
    assert rep["nuevos"] == 14 and rep["nuevos_con_correo"] == 2 and "Kennedy Central: 14" in rep["mensaje"]


def test_plan_rota_zonas_y_usa_la_pagina_siguiente(client, pg_url):
    _run(pg_url, """UPDATE prospect_settings SET config = '{"search_limits": {"restaurante": 40, "bar": 40, "taller": 40},
                    "zone_search_limit": 40}'::jsonb""", fetch=False)
    food = "&tipos=restaurante,comidas_rapidas,cafe,panaderia"
    plan = client.get(f"{URL}/n8n/scan-plan?max=40{food}", headers=H).json()["plan"]
    assert len(plan) == 24 and all(not p["zone"].startswith("bogota-") for p in plan), "comida solo en Kennedy/Techo/Hipotecho"
    _ingest(client, pg_url, [], next_page_token="PAG2")
    plan = client.get(f"{URL}/n8n/scan-plan?max=40{food}", headers=H).json()["plan"]
    kc = [p for p in plan if p["zone"] == "kennedy-central" and p["business_type"] == "restaurante"]
    assert kc and kc[0]["request"]["body"]["pageToken"] == "PAG2"
    _ingest(client, pg_url, [], next_page_token="")
    plan = client.get(f"{URL}/n8n/scan-plan?max=40{food}", headers=H).json()["plan"]
    assert not [p for p in plan if p["zone"] == "kennedy-central" and p["business_type"] == "restaurante"], "no se repite en 30 dias"
    only = client.get(f"{URL}/n8n/scan-plan?max=40&zona=kennedy&tipos=bar,cafe", headers=H).json()["plan"]
    assert {p["zone"] for p in only} == {"kennedy-central", "castilla", "americas", "timiza"} and {p["business_type"] for p in only} == {"bar", "cafe"}


def test_refresco_cada_30_dias(client, pg_url):
    _ingest(client, pg_url, _kennedy_20())
    assert client.get(f"{URL}/n8n/refresh-due", headers=H).json()["items"] == []
    _run(pg_url, "UPDATE prospects SET place_refreshed_at = now() - interval '31 days' WHERE place_id = 'place-1'", fetch=False)
    due = client.get(f"{URL}/n8n/refresh-due", headers=H).json()["items"]
    assert [d["place_id"] for d in due] == ["place-1"]
    r = client.post(f"{URL}/n8n/refresh", headers=H, json={"prospect_id": due[0]["id"], "place": {**_place(1, "Sabor de Casa"), "businessStatus": "CLOSED_PERMANENTLY"}})
    assert r.json()["estado"] == "CLOSED_PERMANENTLY"
    row = _run(pg_url, "SELECT name, business_status, place_refreshed_at > now() - interval '1 minute' AS fresh FROM prospects WHERE place_id = 'place-1'")[0]
    assert row == {"name": "Sabor de Casa", "business_status": "CLOSED_PERMANENTLY", "fresh": True}


# ------------------------------------------------------------------ lote, horario y reglas de contacto
def _batch(pg_url, at):
    return _with_db(pg_url, lambda db: ps.build_batch(db, at))


def _claim(pg_url, at):
    return _with_db(pg_url, lambda db: ps.claim_next(db, at))


def _sent(pg_url, cid, at):
    return _with_db(pg_url, lambda db: ps.mark_sent(db, cid, message_id="m", thread_id=f"thread-{cid}", at=at))


def test_lote_aprobacion_horario_espaciado_y_seguimiento_unico(client, pg_url):
    _ingest(client, pg_url, _kennedy_20())
    tue = _at(2026, 11, 10, 7, 30)
    view = _batch(pg_url, tue)
    assert [i["name"] for i in view["items"]] == ["Panadería La Espiga", "Restaurante Doña Rosa 1"]
    assert all(i["status"] == "pendiente" for i in view["items"])
    assert _batch(pg_url, tue)["batch"]["id"] == view["batch"]["id"], "un lote por dia"
    # sin aprobar no sale nada, ni en horario
    assert _claim(pg_url, _at(2026, 11, 10, 9))["motivo"] == "nada_pendiente"
    bid = view["batch"]["id"]
    with pytest.raises(ValueError):  # un lote solo se aprueba el mismo dia
        _with_db(pg_url, lambda db: ps.decide_batch(db, bid, True, at=_at(2026, 11, 11, 7)))
    _with_db(pg_url, lambda db: ps.decide_batch(db, bid, True, at=tue))
    assert _claim(pg_url, _at(2026, 11, 10, 7, 59))["motivo"] == "fuera_de_horario"
    first = _claim(pg_url, _at(2026, 11, 10, 8, 0))["item"]
    assert first["to"] == "pedidos@laespiga.com.co" and "carta en video" in first["subject"] and "utm_content=" in first["html"]
    assert _claim(pg_url, _at(2026, 11, 10, 8, 3))["motivo"] == "espaciado", "no todos en el mismo minuto"
    _sent(pg_url, first["contact_id"], _at(2026, 11, 10, 8, 1))
    second = _claim(pg_url, _at(2026, 11, 10, 8, 10))["item"]
    _sent(pg_url, second["contact_id"], _at(2026, 11, 10, 8, 11))
    assert _claim(pg_url, _at(2026, 11, 10, 8, 30))["motivo"] == "nada_pendiente"
    p = _run(pg_url, "SELECT status, contact_count FROM prospects WHERE email = 'pedidos@laespiga.com.co'")[0]
    assert p == {"status": "contactado", "contact_count": 1}
    # 1 contacto por semana: al dia siguiente no hay nadie que contactar
    assert _batch(pg_url, _at(2026, 11, 11, 7, 30))["motivo"] == "sin_prospectos"
    # a los 7 dias: seguimiento (el 17 a las 7:30 aun no se cumplen; el 18 si)
    assert _batch(pg_url, _at(2026, 11, 17, 7, 30))["motivo"] == "sin_prospectos"
    fol = _batch(pg_url, _at(2026, 11, 18, 7, 30))
    assert {i["kind"] for i in fol["items"]} == {"seguimiento"} and len(fol["items"]) == 2
    _with_db(pg_url, lambda db: ps.decide_batch(db, fol["batch"]["id"], True, at=_at(2026, 11, 18, 7, 31)))
    f1 = _claim(pg_url, _at(2026, 11, 18, 9))["item"]
    assert f1["subject"].startswith("Re: ")
    _sent(pg_url, f1["contact_id"], _at(2026, 11, 18, 9, 1))
    # despues del seguimiento: nada mas, nunca
    later = _batch(pg_url, _at(2026, 12, 15, 7, 30))
    names = [i["name"] for i in later["items"]]
    assert "Panadería La Espiga" not in names


def test_sabado_festivo_y_tarde_no_hay_lote(client, pg_url):
    _ingest(client, pg_url, _kennedy_20())
    assert _batch(pg_url, _at(2026, 11, 14, 8))["motivo"] == "fin_de_semana"
    assert _batch(pg_url, _at(2026, 11, 16, 8))["motivo"] == "festivo"
    assert _batch(pg_url, _at(2026, 11, 10, 17, 5))["motivo"] == "fuera_de_horario"


def test_saltar_hoy_no_envia_y_quedan_para_otro_dia(client, pg_url):
    _ingest(client, pg_url, _kennedy_20())
    v = _batch(pg_url, _at(2026, 11, 10, 7, 30))
    _with_db(pg_url, lambda db: ps.decide_batch(db, v["batch"]["id"], False, at=_at(2026, 11, 10, 7, 31)))
    assert _claim(pg_url, _at(2026, 11, 10, 9))["motivo"] == "nada_pendiente"
    assert len(_batch(pg_url, _at(2026, 11, 11, 7, 30))["items"]) == 2


def test_endpoint_de_lote_hoy_y_mensaje_para_telegram(client, pg_url, monkeypatch):
    _ingest(client, pg_url, _kennedy_20())
    monkeypatch.setattr(ps, "now", lambda: _at(2026, 11, 10, 7, 30).astimezone(timezone.utc))
    r = client.post(f"{URL}/n8n/batch/today", headers=H).json()
    assert r["enviar_aviso"] is True and len(r["items"]) == 2
    assert "Panadería La Espiga · Kennedy Central · Panadería · pedidos@laespiga.com.co" in r["mensaje"]
    prev = client.get(r["preview_url"].split("railway.app", 1)[-1] if "railway.app" in r["preview_url"] else r["preview_url"])
    assert prev.status_code == 200 and "No quiero recibir más correos" in prev.text
    d = client.post(f"{URL}/n8n/batch/{r['batch']['id']}/decide", headers=H, json={"accion": "enviar"}).json()
    assert d["status"] == "aprobado" and "LOTE APROBADO" in d["mensaje"]
    d2 = client.post(f"{URL}/n8n/batch/{r['batch']['id']}/decide", headers=H, json={"accion": "saltar"}).json()
    assert "ya estaba aprobado" in d2["mensaje"]


def test_baja_por_enlace_bloquea_envios_futuros(client, pg_url):
    _ingest(client, pg_url, _kennedy_20())
    v = _batch(pg_url, _at(2026, 11, 10, 7, 30))
    _with_db(pg_url, lambda db: ps.decide_batch(db, v["batch"]["id"], True, at=_at(2026, 11, 10, 7, 31)))
    tok = _run(pg_url, "SELECT unsub_token FROM prospects WHERE email = 'pedidos@laespiga.com.co'")[0]["unsub_token"]
    page = client.get(f"{URL}/baja?t={tok}")
    assert page.status_code == 200 and "No recibirás más correos" in page.text and page.headers["cache-control"] == "no-store"
    assert "ya estabas" in client.get(f"{URL}/baja?t={tok}").text.lower()
    item = _claim(pg_url, _at(2026, 11, 10, 9))["item"]
    assert item["to"] == "info@sabordecasa.co", "el que se dio de baja ya no sale"
    ex = _run(pg_url, "SELECT kind, value, reason FROM prospect_exclusions ORDER BY kind")
    assert {"kind": "email", "value": "pedidos@laespiga.com.co", "reason": "baja"} in ex
    # aunque vuelva a aparecer en Google con otro place_id, el correo esta excluido
    _ingest(client, pg_url, [{**_place(99, "Panadería La Espiga Sede 2", web="https://laespiga.com.co/"), "primaryType": "bakery"}])
    assert _run(pg_url, "SELECT email, email_status FROM prospects WHERE place_id = 'place-99'")[0] == {"email": "", "email_status": "excluido"}
    assert client.post(f"{URL}/baja?t={tok}").json() == {"ok": True}


def test_respuestas_por_correo(client, pg_url):
    _ingest(client, pg_url, _kennedy_20())
    r = client.post(f"{URL}/n8n/inbound-email", headers=H, json={"de": "Info@SaborDeCasa.co", "asunto": "Re: carta", "cuerpo": "Hola, ¿cómo funciona? Me interesa"}).json()
    assert r["es_prospecto"] and not r["baja"] and "respondió" in r["aviso"]
    assert _run(pg_url, "SELECT status FROM prospects WHERE email = 'info@sabordecasa.co'")[0]["status"] == "respondio"
    no = client.post(f"{URL}/n8n/inbound-email", headers=H, json={"de": "pedidos@laespiga.com.co", "asunto": "Re: x", "cuerpo": "No gracias\n\n> hola"}).json()
    assert no["baja"] and "NO" in no["aviso"]
    assert _run(pg_url, "SELECT status FROM prospects WHERE email = 'pedidos@laespiga.com.co'")[0]["status"] == "baja"
    other = client.post(f"{URL}/n8n/inbound-email", headers=H, json={"de": "alguien@otro.com", "cuerpo": "hola"}).json()
    assert other == {"prospecto": None, "baja": False, "es_prospecto": False, "aviso": ""}
    assert _batch(pg_url, _at(2026, 11, 10, 7, 30))["motivo"] == "sin_prospectos", "ni respondio ni baja reciben mas"


def test_correos_de_prueba_solo_a_clonexa_y_la_baja_los_bloquea(client, pg_url):
    _run(pg_url, "UPDATE prospect_settings SET config = '{\"test_recipient\": \"equipo@clonexa.test\"}'::jsonb", fetch=False)
    items = client.post(f"{URL}/n8n/test-emails", headers=H).json()["items"]
    assert [i["to"] for i in items] == ["equipo+carta@clonexa.test", "equipo+bar@clonexa.test", "equipo+taller@clonexa.test",
                                        "equipo+campo@clonexa.test", "equipo+transporte@clonexa.test", "equipo+tienda@clonexa.test"]
    pages = [i["demo_url"].split("?")[0] for i in items]
    assert pages == ["https://www.clonexa.com.co/restaurantes", "https://www.clonexa.com.co/bares", "https://www.clonexa.com.co/talleres-y-fabricas",
                     "https://www.clonexa.com.co/personal-en-campo", "https://www.clonexa.com.co/", "https://www.clonexa.com.co/"]
    assert all("Negocio en vivo 3D" in i["html"] for i in items)
    assert all(i["subject"].startswith("[PRUEBA] ") and not i["bloqueado"] for i in items)
    client.post(f"{URL}/n8n/outbox/{items[0]['contact_id']}/sent", headers=H, json={"message_id": "x", "thread_id": "y"})
    tok = items[0]["unsub_url"].split("t=", 1)[1]
    assert client.get(f"{URL}/baja?t={tok}").status_code == 200
    again = client.post(f"{URL}/n8n/test-emails", headers=H).json()["items"]
    assert again[0]["bloqueado"] is True and not again[1]["bloqueado"]
    assert _run(pg_url, "SELECT COUNT(*)::int AS n FROM prospects WHERE is_test")[0]["n"] == 6
    _admin_map = _with_db(pg_url, lambda db: ps.map_data(db, {}))
    assert _admin_map["pins"] == [] and _admin_map["cards"]["prospectos"] == 0, "las pruebas no salen en el mapa"


# ------------------------------------------------------------------ landing y WhatsApp
class Reader:
    def get(self, ip):
        return {"country": {"iso_code": "CO"}, "subdivisions": [{"names": {"en": "Bogota D.C."}}],
                "city": {"names": {"en": "Bogotá"}}, "location": {"latitude": 4.6097, "longitude": -74.0817}} if ip.startswith("190.") else None


@pytest.fixture
def geo():
    ip_geo.set_reader(Reader())
    yield
    ip_geo._STATE.update({"reader": None, "path": None, "failed": False})


def _visit(c, ip, **utm):
    return c.post("/api/v1/landing-analytics/events", json={"event_type": "page_view", "url": "https://www.clonexa.com.co/", "path": "/", **utm},
                  headers={"X-Forwarded-For": f"{ip}, 10.0.0.1"})


def test_visita_con_utm_del_prospecto_marca_abrio(client, pg_url, geo):
    _ingest(client, pg_url, _kennedy_20())
    code = _run(pg_url, "SELECT code FROM prospects WHERE email = 'info@sabordecasa.co'")[0]["code"]
    assert _visit(client, "190.24.10.10", utm_source="email", utm_medium="prospeccion", utm_campaign="kennedy-central-restaurante",
                  utm_content=code).status_code == 200
    p = _run(pg_url, "SELECT id::text AS id, status, opened_at IS NOT NULL AS abrio FROM prospects WHERE code = :c", {"c": code})[0]
    assert p["status"] == "abrio" and p["abrio"]
    ev = _run(pg_url, "SELECT ip_address, ip_hash, city, lat, prospect_id::text AS pid, content FROM landing_visit_events")[0]
    assert ev["pid"] == p["id"] and ev["content"] == code
    # otro medium con el mismo codigo NO marca (solo prospeccion)
    other = _run(pg_url, "SELECT code FROM prospects WHERE email = 'pedidos@laespiga.com.co'")[0]["code"]
    _visit(client, "190.24.10.11", utm_source="email", utm_medium="social", utm_content=other)
    assert _run(pg_url, "SELECT status FROM prospects WHERE code = :c", {"c": other})[0]["status"] == "nuevo"
    hist = _run(pg_url, "SELECT kind FROM prospect_contacts WHERE prospect_id = CAST(:i AS uuid)", {"i": p["id"]})
    assert [h["kind"] for h in hist] == ["apertura"]


def test_visita_normal_ciudad_aproximada_e_ip_no_completa(client, pg_url, geo):
    _visit(client, "190.24.10.77")
    ev = _run(pg_url, "SELECT ip_address, ip_hash, country, region, city, lat, lng, geo_source FROM landing_visit_events")[0]
    assert ev["ip_address"] == "190.24.10.0" and "190.24.10.77" not in str(ev) and len(ev["ip_hash"]) == 32
    assert (ev["country"], ev["city"], ev["lat"], ev["geo_source"]) == ("CO", "Bogotá", 4.6097, "dbip")
    # visitas viejas con la IP completa: se ubican y se recortan
    _run(pg_url, "INSERT INTO landing_visit_events (ip_address) VALUES ('190.99.1.2'), ('')", fetch=False)
    n = _with_db(pg_url, lambda db: landing_analytics.backfill_geo(db))
    assert n == 2
    rows = _run(pg_url, "SELECT ip_address, ip_hash, city FROM landing_visit_events ORDER BY created_at")
    assert {"ip_address": "190.99.1.0", "city": "Bogotá"}.items() <= next(r for r in rows if r["ip_address"].startswith("190.99")).items()
    assert not any(r["ip_address"] in ("190.99.1.2", "190.24.10.77") for r in rows) and all(r["ip_hash"] for r in rows)


def test_whatsapp_con_codigo_se_liga_al_prospecto(pg_url, client, monkeypatch):
    _ingest(client, pg_url, _kennedy_20())
    code = _run(pg_url, "SELECT code FROM prospects WHERE email = 'info@sabordecasa.co'")[0]["code"]
    forwarded, alerts = [], []

    async def fwd(body):
        forwarded.append(body)
        return True

    async def send(wa, body):
        return {"ok": True, "meta_id": "x"}

    async def alert(t):
        alerts.append(t)
        return True

    monkeypatch.setattr(nw, "_deliver_alert", alert)
    nw.PER_NUMBER.hits.clear()
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": nw.phone_id()}, "contacts": [{"profile": {"name": "Sabor"}, "wa_id": "573001112233"}],
        "messages": [{"from": "573001112233", "id": "wamid.p1", "timestamp": str(int(time.time())), "type": "text",
                      "text": {"body": f"Hola, vi la carta video (código {code})"}}]}}]}]}
    out = _with_db(pg_url, lambda db: nw.process_webhook(db, payload, send=send, fwd=fwd))
    assert out["forwarded"] == 1
    assert forwarded[0]["prospecto"]["codigo"] == code and forwarded[0]["prospecto"]["tipo"] == "restaurante"
    p = _run(pg_url, "SELECT status, wa_consent_at IS NOT NULL AS consent, wa_consent_source FROM prospects WHERE code = :c", {"c": code})[0]
    assert p == {"status": "respondio", "consent": True, "wa_consent_source": "escribio_con_codigo"}
    assert alerts and code in alerts[0]
    # sin codigo: no se liga y el reenvio no trae prospecto
    payload["entry"][0]["changes"][0]["value"]["messages"][0].update({"id": "wamid.p2", "text": {"body": "hola, info"}})
    _with_db(pg_url, lambda db: nw.process_webhook(db, payload, send=send, fwd=fwd))
    assert forwarded[1]["prospecto"] is None and len(alerts) == 1


# ------------------------------------------------------------------ consola: mapa comercial
def test_mapa_tarjetas_zonas_pines_y_ficha(client, pg_url, monkeypatch, geo):
    _admin(monkeypatch)
    _ingest(client, pg_url, _kennedy_20())
    _visit(client, "190.24.10.10")
    code = _run(pg_url, "SELECT code FROM prospects WHERE email = 'info@sabordecasa.co'")[0]["code"]
    _visit(client, "190.24.10.10", utm_medium="prospeccion", utm_content=code)
    client.post(f"{URL}/n8n/inbound-email", headers=H, json={"de": "info@sabordecasa.co", "cuerpo": "me interesa"})
    m = client.get(f"{URL}/admin/map").json()
    assert m["cards"]["prospectos"] == 14 and m["cards"]["con_correo"] == 2 and m["cards"]["abrieron"] == 1 and m["cards"]["respondieron"] == 1
    kc = next(z for z in m["zones"] if z["slug"] == "kennedy-central")
    assert kc["prospectos"] == 14 and kc["puntaje"] == ps.zone_score(kc)
    assert len([z for z in m["zones"] if z["group_name"] != "Bogotá"]) == 6 and len(m["zones"]) == 25
    rest = next(n for n in m["niches"] if n["key"] == "restaurante")
    assert rest["prospectos"] == 14 and rest["page"] == "/restaurantes" and {n["key"] for n in m["niches"]} == set(ps.NICHES)
    assert all(p["niche"] == "restaurante" for p in m["pins"])
    assert client.get(f"{URL}/admin/map?nicho=taller").json()["pins"] == []
    pin = next(p for p in m["pins"] if p["name"] == "Panadería La Espiga")
    assert pin["email"] == "p•••@laespiga.com.co" and "pedidos@" not in str(m["pins"])
    assert m["heat_visits"] and m["heat_visits"][0]["city"] == "Bogotá" and m["heat_visits"][0]["total"] == 2
    assert m["heat_leads"] and m["attribution"]["ip"] == "IP Geolocation by DB-IP"
    f = client.get(f"{URL}/admin/map?tipo=panaderia").json()
    assert [p["name"] for p in f["pins"]] == ["Panadería La Espiga"]
    assert [p["status"] for p in client.get(f"{URL}/admin/map?estado=respondio").json()["pins"]] == ["respondio"]
    d = client.get(f"{URL}/admin/prospects/{pin['id']}").json()
    assert d["prospect"]["email"] == "pedidos@laespiga.com.co" and "query_place_id=place-0" in d["prospect"]["maps_url"]
    st = client.post(f"{URL}/admin/prospects/{pin['id']}/status", json={"estado": "demo"}).json()
    assert st["prospect"]["status"] == "demo"
    assert client.post(f"{URL}/admin/prospects/{pin['id']}/status", json={"estado": "nuevo"}).status_code == 422


def test_zonas_nuevas_y_cadenas_desde_la_consola(client, pg_url, monkeypatch):
    _admin(monkeypatch)
    r = client.post(f"{URL}/admin/zones", json={"name": "Chapinero Central", "group_name": "Chapinero", "center_lat": 4.645, "center_lng": -74.063, "radius_m": 800})
    assert r.status_code == 200 and r.json()["zone"]["slug"] == "chapinero-central"
    assert client.post(f"{URL}/admin/zones", json={"name": "Chapinero Central", "center_lat": 4.645, "center_lng": -74.063}).status_code == 409
    assert client.post(f"{URL}/admin/zones", json={"name": "Madrid", "center_lat": 40.4, "center_lng": -3.7}).status_code == 422
    poly = client.post(f"{URL}/admin/zones", json={"name": "Poligono", "center_lat": 4.62, "center_lng": -74.15,
                                                   "polygon": [[4.60, -74.16], [4.64, -74.16], [4.64, -74.13]]}).json()["zone"]
    assert poly["kind"] == "polygon"
    plan = client.get(f"{URL}/n8n/scan-plan?max=40&zona=chapinero-central", headers=H).json()["plan"]
    assert len(plan) == 6
    names = client.put(f"{URL}/admin/chains", json={"names": ["Frisby", "Nueva Cadena"]}).json()["chains"]
    assert names == ["Frisby", "Nueva Cadena"]
    out = _ingest(client, pg_url, [_place(1, "Nueva Cadena Kennedy"), _place(2, "KFC ya no es cadena aqui")]).json()
    assert out["chain"] == 1 and out["new"] == 1
    s = client.put(f"{URL}/admin/settings", json={"daily_limit": 25, "signature": "Equipo Clonexa"}).json()["settings"]
    assert s["daily_limit"] == 25 and s["signature"] == "Equipo Clonexa"
    assert client.put(f"{URL}/admin/settings", json={"daily_limit": 26}).status_code == 422


# ------------------------------------------------------------------ 025p: nichos
def _bog(pg_url, slug="bogota-puente-aranda"):
    return _zone(pg_url, slug)


def _ingest_in(c, zone, btype, places, **kw):
    return c.post(f"{URL}/n8n/places", headers=H, json={"zone_id": zone["id"], "business_type": btype, "places": places, **kw})


def test_plan_por_nicho_respeta_limites_diarios_y_prioridad(client, pg_url):
    plan = client.get(f"{URL}/n8n/scan-plan?max=40", headers=H).json()["plan"]
    by = {}
    for p in plan:
        by[p["niche"]] = by.get(p["niche"], 0) + 1
    assert all(by.get(n, 0) <= lim for n, lim in ps.pn.DEFAULT_SEARCH_LIMITS.items()), by
    assert sum(by.values()) <= ps.pn.DAILY_MAX_SEARCHES
    per_zone = {}
    for p in plan:
        per_zone[p["zone"]] = per_zone.get(p["zone"], 0) + 1
    assert max(per_zone.values()) <= ps.pn.DEFAULT_ZONE_LIMIT
    assert by.get("campo") == 12 and by.get("taller") == 8 and by.get("restaurante") == 8, "prioridad 1 y restaurantes llenan su cupo"
    assert all(p["niche"] != "restaurante" or not p["zone"].startswith("bogota-") for p in plan)
    campo = client.get(f"{URL}/n8n/scan-plan?max=40&nicho=campo", headers=H).json()["plan"]
    assert campo and {p["niche"] for p in campo} == {"campo"}
    assert {p["business_type"] for p in campo} <= {"electrico", "telecom", "construccion", "instalador", "aseo", "vigilancia"}
    # lo gastado hoy cuenta: 12 busquedas de campo ya hechas -> el plan de campo queda vacio
    z = _bog(pg_url)
    for _ in range(12):
        _ingest_in(client, z, "electrico", [])
    assert client.get(f"{URL}/n8n/scan-plan?max=40&nicho=campo", headers=H).json()["plan"] == []
    used = _run(pg_url, "SELECT SUM(calls)::int AS n FROM prospect_api_usage WHERE kind = 'places_text' AND niche = 'campo'")[0]["n"]
    assert used == 12
    req = campo[0]["request"]
    assert "(" not in req["body"]["textQuery"] and req["body"]["textQuery"].endswith(", Bogotá")


def _taller(i, name, **kw):
    p = _place(100 + i, name, lat=4.6150, lng=-74.1100, primary="clothing_store", **kw)
    p["addressComponents"] = [{"types": ["neighborhood"], "longText": "Puente Aranda"}]
    return p


def test_talleres_en_bogota_sin_cadenas_del_nicho(client, pg_url, monkeypatch):
    _admin(monkeypatch)
    z = _bog(pg_url)
    places = [_taller(i, f"Confecciones Doña Marta {i}") for i in range(15)] + [_taller(50, "Offcorss Puente Aranda"), _taller(51, "Leonisa Fábrica")]
    out = _ingest_in(client, z, "taller", places).json()
    assert out["new"] == 15 and out["chain"] == 2, out
    rows = _run(pg_url, "SELECT niche, business_type FROM prospects")
    assert {(r["niche"], r["business_type"]) for r in rows} == {("taller", "taller")}
    # cadenas del nicho se editan desde la consola
    names = client.put(f"{URL}/admin/niches/taller/chains", json={"names": ["Confecciones Doña Marta 99", "Offcorss"]}).json()["chains"]
    assert names == ["Confecciones Doña Marta 99", "Offcorss"]
    assert client.put(f"{URL}/admin/niches/inventado/chains", json={"names": []}).status_code == 404
    n = client.get(f"{URL}/admin/niches").json()
    assert {x["key"] for x in n["niches"]} == set(ps.NICHES) and set(n["missing_pages"]) == {"transporte", "tienda"}
    tl = next(x for x in n["niches"] if x["key"] == "taller")
    assert tl["page"] == "talleres-y-fabricas" and "Offcorss" in tl["chains"] and set(tl["types"]) == {"taller", "fabrica"}
    again = _ingest_in(client, z, "taller", [_taller(99, "Confecciones Doña Marta 99"), _taller(52, "Gef Centro")]).json()
    assert again["chain"] == 1 and again["new"] == 1, "Gef ya no esta en la lista del nicho"


@pytest.mark.parametrize("method,path", [("get", "/admin/niches"), ("put", "/admin/niches/taller/chains")])
def test_nichos_sin_sesion_401(client, monkeypatch, method, path):
    _admin(monkeypatch, ok=False)
    assert client.request(method.upper(), URL + path, json={"names": []}, headers=H).status_code == 401


# ------------------------------------------------------------------ 025p: vigencia
def test_vigencia_por_verificar_no_entra_a_correo_y_se_ve_en_mapa(client, pg_url, monkeypatch):
    _admin(monkeypatch)
    places = [_place(300, "Taller Activo", web="https://sabordecasa.co/"),
              _place(301, "Taller Sin Horario", web="https://laespiga.com.co/", hours=False, reviews=0)]
    out = _ingest(client, pg_url, places).json()
    assert out["new"] == 2 and out["with_email"] == 2
    rows = {r["name"]: r for r in _run(pg_url, "SELECT name, vigencia, vigencia_reason, rating_count, has_hours FROM prospects")}
    assert rows["Taller Activo"]["vigencia"] == "activo" and rows["Taller Activo"]["rating_count"] == 25 and rows["Taller Activo"]["has_hours"]
    assert rows["Taller Sin Horario"]["vigencia"] == "por_verificar" and "12 meses" in rows["Taller Sin Horario"]["vigencia_reason"]
    view = _with_db(pg_url, lambda db: ps.build_batch(db, _at(2026, 11, 11, 7, 30)))
    assert [i["name"] for i in view["items"]] == ["Taller Activo"], "por verificar no entra al lote de correo"
    m = client.get(f"{URL}/admin/map?vigencia=por_verificar").json()
    assert [p["name"] for p in m["pins"]] == ["Taller Sin Horario"] and m["pins"][0]["vigencia"] == "por_verificar"
    assert m["cards"]["por_verificar"] == 1
    pid = m["pins"][0]["id"]
    d = client.get(f"{URL}/admin/prospects/{pid}").json()["prospect"]
    assert d["vigencia"] == "por_verificar" and d["vigencia_reason"]
    # refresco de 30 dias: llegaron resenas nuevas -> activo
    _run(pg_url, "UPDATE prospects SET rating_count = 2 WHERE id = CAST(:i AS uuid)", {"i": pid}, fetch=False)
    r = client.post(f"{URL}/n8n/refresh", headers=H, json={"prospect_id": pid, "place": {**places[1], "userRatingCount": 4}}).json()
    assert r["vigencia"] == "activo"
    assert _run(pg_url, "SELECT SUM(calls)::int AS n FROM prospect_api_usage WHERE kind = 'places_details'")[0]["n"] == 1
    # ya no aparece en Google -> por verificar
    r = client.post(f"{URL}/n8n/refresh", headers=H, json={"prospect_id": pid, "not_found": True}).json()
    assert _run(pg_url, "SELECT vigencia FROM prospects WHERE id = CAST(:i AS uuid)", {"i": pid})[0]["vigencia"] == "por_verificar"
