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
            client.post(f"{URL}/n8n/fail", headers=H, json={"informe_id": r["informe_id"], "error": "antes de Claude"})
            again = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "a_pedido", "tema": "t0"}).json()
            assert again["ok"], "uno que fallo sin gastar no cuenta en el tope"
            r = again
        _run(pg_url, "UPDATE radar_informes SET costo_usd = 0.05 WHERE id = :i", {"i": r["informe_id"]}, fetch=False)
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


# ------------------------------------------------------------------ punto 2: informe con Claude (respuesta simulada)
import json as _json  # noqa: E402

from app.services import radar_ai as ai  # noqa: E402


def _claude(ideas, urls, *, stop="end_turn", searches=3):
    return {"type": "message", "model": "claude-sonnet-5-5", "stop_reason": stop,
            "content": [{"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "x"}},
                        {"type": "web_search_tool_result", "tool_use_id": "s1",
                         "content": [{"type": "web_search_result", "url": u, "title": "t"} for u in urls]},
                        {"type": "text", "text": _json.dumps({"ideas": ideas}, ensure_ascii=False)}],
            "usage": {"input_tokens": 20000, "output_tokens": 3000, "cache_read_input_tokens": 1000, "server_tool_use": {"web_search_requests": searches}}}


SRC = "https://innpulsacolombia.com/convocatorias/software-2026"


def _raw(t, url=SRC, fecha="2026-11-02", **kw):
    return {"titulo": t, "resumen": "r", "por_que": "p", "categoria": "fondos", "impacto": "alto", "esfuerzo": "medio", "costo": "bajo",
            "costo_estimado": "US$0", "fecha_limite": "2026-12-05", "fuentes": [{"url": url, "titulo": "iNNpulsa", "fecha": fecha}], **kw}


def test_peticion_a_claude_con_busqueda_web_y_tope(client, monkeypatch):
    r = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "a_pedido", "tema": "fondos para startups de software en Colombia",
                                                          "origen": "telegram"}).json()
    req = r["request"]
    assert req["model"] == "claude-sonnet-5-5" and req["output_config"] == {"effort": "medium"}
    tool = req["tools"][0]
    assert tool == {"type": "web_search_20260209", "name": "web_search", "max_uses": 8}, "sin user_location: la API no acepta CO"
    assert "fondos para startups de software en Colombia" in req["messages"][0]["content"] and "Trae 3 ideas" in req["messages"][0]["content"]
    assert "Herramientas y APIs que nos sirvan" in req["messages"][0]["content"], "temas activos de la tabla"


def test_sin_fuente_o_fuente_inventada_se_descarta_y_repetida_no_sale(client, pg_url):
    inf = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "a_pedido", "tema": "fondos"}).json()
    ideas = [_raw("Convocatoria iNNpulsa para empresas de software"),
             _raw("Idea sin fuente alguna", fuentes=[]),
             _raw("Idea con fuente inventada fuera de la búsqueda", url="https://inventado.example/x"),
             _raw("Idea con fuente sin fecha", fecha=""),
             _raw("MinTIC abre fondo de apps", url="https://www.mintic.gov.co/portal/fondo-apps")]
    resp = _claude(ideas, [SRC, "https://mintic.gov.co/portal/fondo-apps/"])
    out = client.post(f"{URL}/n8n/finish", headers=H, json={"informe_id": inf["informe_id"], "request": inf["request"], "responses": [resp]}).json()
    assert out["ok"] and len(out["ideas"]) == 2 and out["descartadas"] == 3
    assert out["cabecera"].startswith("🛰️ <b>Radar a pedido · fondos · 2 ideas</b>")
    one = out["ideas"][0]
    assert set(one["botones"]) == {"interesa", "backlog", "descartar"} and SRC in out["ideas"][0]["mensaje"] + out["ideas"][1]["mensaje"]
    row = _run(pg_url, "SELECT costo_usd::float AS c, busquedas, n_ideas, descartadas, estado, tokens_in FROM radar_informes WHERE id = :i",
               {"i": inf["informe_id"]})[0]
    # 20.000 * 2 + 3.000 * 10 + 1.000 * 0.1 por millon + 3 busquedas * 0,01
    assert row == {"c": 0.1001, "busquedas": 3, "n_ideas": 2, "descartadas": 3, "estado": "listo", "tokens_in": 21000}
    inf2 = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "a_pedido", "tema": "fondos"}).json()
    again = client.post(f"{URL}/n8n/finish", headers=H, json={"informe_id": inf2["informe_id"], "request": inf2["request"],
                                                              "responses": [_claude([_raw("Convocatoria de iNNpulsa para empresas de software")], [SRC])]}).json()
    assert again["ok"] and again["ideas"] == [] and again["repetidas"] == 1 and "sin ideas nuevas" in again["cabecera"]
    assert "Convocatoria iNNpulsa para empresas de software" in inf2["request"]["messages"][0]["content"], "Claude ve lo ya propuesto"


def test_error_de_claude_o_sin_json_falla_con_aviso(client, pg_url):
    inf = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "semanal"}).json()
    bad = client.post(f"{URL}/n8n/finish", headers=H, json={"informe_id": inf["informe_id"],
                                                            "responses": [{"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}]}).json()
    assert bad["ok"] is False and "Overloaded" in bad["mensaje"]
    assert _with_db(pg_url, lambda db: rd.office_snapshot(db))["state"] == "err"
    inf2 = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "semanal"}).json()
    nojs = {"stop_reason": "end_turn", "content": [{"type": "text", "text": "No encontré nada"}], "usage": {}}
    assert client.post(f"{URL}/n8n/finish", headers=H, json={"informe_id": inf2["informe_id"], "responses": [nojs]}).json()["ok"] is False
    assert client.post(f"{URL}/n8n/fail", headers=H, json={"error": "timeout"}).json()["ok"]


def test_pause_turn_continua_con_lo_hecho(client):
    req = {"model": "m", "messages": [{"role": "user", "content": "hola"}]}
    r = client.post(f"{URL}/n8n/continue", headers=H, json={"informe_id": 1, "request": req,
                                                            "responses": [{"stop_reason": "pause_turn", "content": [{"type": "text", "text": "..."}]}]}).json()
    assert r["request"]["messages"][-1] == {"role": "assistant", "content": [{"type": "text", "text": "..."}]}


def test_generar_desde_la_consola_respeta_el_tope(client, pg_url, monkeypatch):
    from app.api.v1.endpoints import radar as ep
    _admin(monkeypatch)
    calls = []

    async def hook(path, payload):
        calls.append((path, payload))
        return True

    monkeypatch.setattr(ep, "_hook", hook)
    assert client.post(f"{URL}/admin/generar", json={"tema": "pagos"}).json()["ok"]
    assert calls == [("nexus-radar", {"tema": "pagos", "origen": "consola"})]
    for i in range(3):
        r = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "a_pedido", "tema": f"t{i}"}).json()
        _with_db(pg_url, lambda db, iid=r["informe_id"]: rd.save_report(db, iid, [], discarded=0, usage={"costo_usd": 0.2}))
    assert client.post(f"{URL}/admin/generar", json={}).status_code == 429
    _admin(monkeypatch, ok=False)
    assert client.post(f"{URL}/admin/generar", json={}).status_code == 401
    assert client.post(f"{URL}/n8n/finish", json={"informe_id": 1}).status_code == 401


def test_recurso_del_modulo_exige_sesion(client, monkeypatch):
    from app.web import admin_v2plus_routes as plus
    monkeypatch.setattr(plus, "_active_session", AsyncMock(return_value=False))
    assert client.get("/admin-v2plus-radar.js").status_code == 401
    monkeypatch.setattr(plus, "_active_session", AsyncMock(return_value=True))
    r = client.get("/admin-v2plus-radar.js")
    assert r.status_code == 200 and "CxConsoleRadar" in r.text


def test_piso_clonexa_trae_el_radar_real(client, pg_url):
    from app.services import oficina_data as od
    from app.services import oficina_pisos as opi
    snap = _with_db(pg_url, lambda db: opi.radar_live(od.Reader(db), datetime.now(timezone.utc)))
    assert snap["state"] == "nodata" and snap["top"] == [] and snap["counts"]["nueva"] == 0
    inf = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "semanal"}).json()["informe_id"]
    assert _with_db(pg_url, lambda db: opi.radar_live(od.Reader(db), datetime.now(timezone.utc)))["state"] == "work"
    _with_db(pg_url, lambda db: rd.save_report(db, inf, [IDEA("Pagos con QR Bre-B en Colombia")], discarded=0, usage={}))
    snap = _with_db(pg_url, lambda db: opi.radar_live(od.Reader(db), datetime.now(timezone.utc)))
    assert snap["state"] == "wait" and snap["top"][0]["titulo"] == "Pagos con QR Bre-B en Colombia" and snap["nuevas"] == 1


def test_resumen_del_ultimo_informe_para_operacion(client, pg_url):
    assert client.get(f"{URL}/n8n/informes/ultimo").status_code == 401
    assert client.get(f"{URL}/n8n/informes/ultimo", headers=H).json() == {"informe": None, "ideas": []}
    inf = client.post(f"{URL}/n8n/start", headers=H, json={"tipo": "semanal"}).json()["informe_id"]
    _with_db(pg_url, lambda db: rd.save_report(db, inf, [IDEA("Bre-B pagos inmediatos para restaurantes")], discarded=2, usage={"costo_usd": 0.31}))
    r = client.get(f"{URL}/n8n/informes/ultimo", headers=H).json()
    assert r["informe"]["costo_usd"] == 0.31 and r["informe"]["descartadas"] == 2 and r["ideas"][0]["titulo"].startswith("Bre-B")
