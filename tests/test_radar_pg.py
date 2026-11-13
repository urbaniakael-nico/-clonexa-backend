"""NEXUS · Radar contra Postgres REAL (pgserver) y la app completa.

- Migracion 025q idempotente y temas iniciales.
- 401 sin token de n8n / sin sesion de Admin V2.
- Tope de 3 informes a pedido por dia; un informe a la vez; "corriendo" viejo = fallido.
- Ideas repetidas (90 dias) no se guardan; orden por puntaje; estados desde Telegram y desde la consola (una sola fuente).
- Copia viva de la oficina: estado de NEXUS, top 3 y conteos REALES (sin ideas: vacio).
"""
from __future__ import annotations

import asyncio
import importlib
import tempfile
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
from app.api.v1.endpoints import prospecting as pep  # noqa: E402
from app.services import radar as rd  # noqa: E402
from app.web import admin_v2_routes  # noqa: E402

TOKEN = "prueba-" + "r" * 40
URL = "/api/v1/radar"
H = {"X-Nexa-Token": TOKEN}
BOG = rd.BOGOTA


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
    folder = tempfile.mkdtemp(prefix="cx_pg_radar_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            for _ in range(2):
                for stmt in _statements("025q_nexus_radar"):
                    await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


def _run(url, sql, params=None, fetch=True):
    async def go():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            r = await conn.execute(text(sql), params or {})
            rows = [dict(x) for x in r.mappings().all()] if fetch else None
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


@pytest.fixture
def client(pg_url, monkeypatch):
    _run(pg_url, "TRUNCATE radar_ideas, radar_informes, radar_ignorados RESTART IDENTITY CASCADE", fetch=False)

    async def db_dep():
        engine = create_async_engine(pg_url, poolclass=NullPool)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            yield session
        await engine.dispose()

    monkeypatch.setenv(pep.TOKEN_ENV, TOKEN)
    pep.N8N_PER_IP.hits.clear()
    app_main.app.dependency_overrides[get_db] = db_dep
    yield TestClient(app_main.app)
    app_main.app.dependency_overrides.pop(get_db, None)


def _admin(monkeypatch, ok=True):
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=ok))


def IDEA(t, imp="alto", ef="medio", co="bajo", url=None, **kw):
    return {"titulo": t, "resumen": "r", "por_que": "p", "categoria": "fondos", "impacto": imp, "esfuerzo": ef, "costo": co,
            "fuentes": [{"url": url or f"https://example.gov.co/{rd.fingerprint(t)[:8]}", "titulo": "x", "fecha": "2026-11-10"}], **kw}


def test_migracion_y_temas_iniciales(pg_url):
    t = _run(pg_url, "SELECT clave, activo FROM radar_temas ORDER BY orden")
    assert [x["clave"] for x in t] == ["herramientas", "competencia", "fondos", "normas", "nichos"] and all(x["activo"] for x in t)
    mod = importlib.import_module("migrations.versions.025q_nexus_radar")
    assert len(mod.revision) <= 32 and mod.down_revision == "025p_prospect_multicanal"


N8N = [("post", "/n8n/start"), ("post", "/n8n/fail"), ("post", "/n8n/ideas/1/state"), ("post", "/n8n/ideas/1/message"),
       ("get", "/n8n/list"), ("get", "/n8n/help"), ("post", "/n8n/ignored")]
ADMIN = [("get", "/admin/ideas"), ("patch", "/admin/ideas/1"), ("get", "/admin/informes"), ("get", "/admin/temas"),
         ("post", "/admin/temas"), ("put", "/admin/temas/1")]


@pytest.mark.parametrize("method,path", N8N)
def test_n8n_sin_token_401(client, monkeypatch, method, path):
    assert client.request(method.upper(), URL + path, json={}).status_code == 401
    assert client.request(method.upper(), URL + path, json={}, headers={"X-Nexa-Token": "otro"}).status_code == 401


@pytest.mark.parametrize("method,path", ADMIN)
def test_consola_sin_sesion_401(client, monkeypatch, method, path):
    _admin(monkeypatch, ok=False)
    assert client.request(method.upper(), URL + path, json={}, headers=H).status_code == 401


def test_tope_diario_un_informe_a_la_vez_y_corriendo_viejo(client, pg_url):
    for i in range(3):
        r = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "a_pedido", "tema": f"t{i}", "origen": "telegram"}).json()
        assert r["ok"] and r["n"] == 3
        if i == 0:
            busy = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "semanal"}).json()
            assert busy["ok"] is False and busy["motivo"] == "ya_corriendo"
        client.post(f"{URL}/n8n/fail", headers=H, json={"informe_id": r["informe_id"], "error": "prueba"})
    four = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "a_pedido", "tema": "x"}).json()
    assert four["ok"] is False and four["motivo"] == "tope_diario" and "máximo 3" in four["mensaje"]
    w = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "semanal"}).json()
    assert w["ok"] and w["n"] == 5, "el semanal no cuenta en el tope"
    _run(pg_url, "UPDATE radar_informes SET created_at = now() - interval '30 minutes' WHERE id = :i", {"i": w["informe_id"]}, fetch=False)
    assert client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "semanal"}).json()["ok"], "corriendo de hace 30 min = fallido"
    assert _run(pg_url, "SELECT estado FROM radar_informes WHERE id = :i", {"i": w["informe_id"]})[0]["estado"] == "fallido"


def test_ideas_repetidas_no_vuelven_orden_por_puntaje_y_estados(client, pg_url, monkeypatch):
    _admin(monkeypatch)
    inf = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "semanal"}).json()["informe_id"]
    out = _with_db(pg_url, lambda db: rd.save_report(db, inf, [IDEA("Convocatoria MinTIC software 2026", "medio"),
                                                               IDEA("WhatsApp catálogo en la API Cloud", "alto", "bajo", "bajo"),
                                                               IDEA("convocatoria mintic 2026 software")], discarded=1,
                                                     usage={"input_tokens": 1000, "output_tokens": 200, "busquedas": 6, "costo_usd": 0.12}))
    assert len(out["ids"]) == 2 and out["repetidas"] == 1
    ideas = client.get(f"{URL}/admin/ideas").json()
    assert [i["titulo"] for i in ideas["ideas"]] == ["WhatsApp catálogo en la API Cloud", "Convocatoria MinTIC software 2026"]
    assert ideas["counts"]["nueva"] == 2
    inf2 = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "a_pedido", "tema": "fondos"}).json()["informe_id"]
    out2 = _with_db(pg_url, lambda db: rd.save_report(db, inf2, [IDEA("Convocatoria MinTIC para software 2026")], discarded=0, usage={}))
    assert out2["ids"] == [] and out2["repetidas"] == 1, "no repetir ideas de los ultimos 90 dias"
    rep = client.get(f"{URL}/admin/informes").json()
    assert rep["informes"][1]["costo_usd"] == 0.12 and rep["informes"][1]["descartadas"] == 2 and rep["informes"][1]["n_ideas"] == 2
    wid = ideas["ideas"][0]["id"]
    tg = client.post(f"{URL}/n8n/ideas/{wid}/state", headers=H, json={"estado": "me_interesa"}).json()
    assert tg["ok"] and "⭐ Me interesa" in tg["mensaje"] and tg["botones"]["backlog"] == f"rx:backlog:{wid}"
    assert client.get(f"{URL}/admin/ideas?estado=me_interesa").json()["ideas"][0]["id"] == wid, "Telegram -> consola"
    p = client.patch(f"{URL}/admin/ideas/{wid}", json={"estado": "backlog", "notas": "revisar con el equipo"}).json()
    assert p["idea"]["estado"] == "backlog" and p["idea"]["notas"] == "revisar con el equipo"
    lst = client.get(f"{URL}/n8n/list?que=backlog", headers=H).json()["mensaje"]
    assert "WhatsApp catálogo" in lst, "consola -> Telegram"
    assert "Sin ideas" not in client.get(f"{URL}/n8n/list", headers=H).json()["mensaje"]
    assert client.post(f"{URL}/n8n/ideas/{wid}/state", headers=H, json={"estado": "inventado"}).status_code == 422
    assert client.patch(f"{URL}/admin/ideas/9999", json={"estado": "hecha"}).status_code == 404


def test_temas_editables(client, monkeypatch):
    _admin(monkeypatch)
    t = client.post(f"{URL}/admin/temas", json={"nombre": "Facturación electrónica en LatAm", "descripcion": "x"}).json()["tema"]
    assert t["activo"] and t["clave"].startswith("facturacion-electronica")
    off = client.put(f"{URL}/admin/temas/{t['id']}", json={"nombre": t["nombre"], "descripcion": "y", "activo": False}).json()["tema"]
    assert off["activo"] is False and off["descripcion"] == "y"
    assert client.put(f"{URL}/admin/temas/9999", json={"nombre": "abc"}).status_code == 404


def test_copia_viva_de_la_oficina_con_datos_reales(client, pg_url):
    snap = _with_db(pg_url, lambda db: rd.office_snapshot(db))
    assert snap["state"] == "nodata" and snap["top"] == [] and snap["nuevas"] == 0
    inf = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "semanal"}).json()["informe_id"]
    assert _with_db(pg_url, lambda db: rd.office_snapshot(db))["state"] == "work", "Investigando"
    _with_db(pg_url, lambda db: rd.save_report(db, inf, [IDEA(t, ["alto", "medio", "bajo"][i % 3]) for i, t in enumerate(
                                               ["Pagos con Nequi en la carta", "Telegram Stars para bots", "Ley de datos reforma", "Competidor lanza KDS"])],
                                               discarded=0, usage={}))
    snap = _with_db(pg_url, lambda db: rd.office_snapshot(db))
    assert snap["state"] == "wait" and len(snap["top"]) == 3 and snap["counts"]["nueva"] == 4 and snap["nuevas"] == 4
    assert snap["top"][0]["puntaje"] >= snap["top"][1]["puntaje"] >= snap["top"][2]["puntaje"]
    assert snap["next_label"].startswith("lunes ")
    inf2 = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "semanal"}).json()["informe_id"]
    client.post(f"{URL}/n8n/fail", headers=H, json={"informe_id": inf2, "error": "x"})
    assert _with_db(pg_url, lambda db: rd.office_snapshot(db))["state"] == "err"


def test_chat_ignorado_solo_huella(client, pg_url):
    import hashlib
    hsh = hashlib.sha256(b"999").hexdigest()
    assert client.post(f"{URL}/n8n/ignored", headers=H, json={"chat_hash": hsh, "tipo": "mensaje"}).json()["ok"]
    assert client.post(f"{URL}/n8n/ignored", headers=H, json={"chat_hash": "999"}).status_code == 422
    assert _run(pg_url, "SELECT chat_hash FROM radar_ignorados") == [{"chat_hash": hsh}]
