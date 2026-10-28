"""Nexa por WhatsApp contra Postgres REAL (pgserver) y la app completa.

- Webhook de Meta: verificacion GET, firma mala 401, sin variable 503, mensaje
  nuevo reenviado a n8n con contacto e historial, duplicado no se procesa dos
  veces, estados de entrega (solo avanzan; antes o despues del registro de n8n),
  pausado no reenvia, "baja" confirma una sola vez y despues no responde, limite
  de 20 por minuto por numero, n8n caido -> "Ya te respondemos en un momento".
- /outbound (n8n): secreto, guarda lo enviado y actualiza datos y etapa.
- Consola (solo Admin V2): lista, filtros, nuevas, detalle, pausar/reanudar,
  no interesado y exportar CSV.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import importlib
import json
import tempfile
import time
from unittest.mock import AsyncMock

import pytest

pgserver = pytest.importorskip("pgserver")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.main as app_main  # noqa: E402
from app.api.deps import get_db  # noqa: E402
from app.api.v1.endpoints import nexa_whatsapp as ep  # noqa: E402
from app.services import nexa_whatsapp as nw  # noqa: E402
from app.web import admin_v2_routes  # noqa: E402

APP_SECRET = "clave-app-" + "s" * 30
VERIFY = "verifica-" + "v" * 30
FORWARD = "reenvio-" + "f" * 40
WA = "573001112233"
URL = "/api/v1/nexa-wa"
ADMIN = "/admin-v2/api/nexa-wa"


def _migration() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module("migrations.versions.024w_nexa_whatsapp")
    module.op = Op()
    module.upgrade()
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_nexa_wa_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            for stmt in _migration():
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


class Fakes:
    def __init__(self):
        self.forwarded: list[dict] = []
        self.sent: list[tuple[str, str]] = []
        self.forward_ok = True
        self.n = 0

    async def fwd(self, payload: dict) -> bool:
        self.forwarded.append(payload)
        return self.forward_ok

    async def send(self, wa_id: str, body: str) -> dict:
        self.n += 1
        self.sent.append((wa_id, body))
        return {"ok": True, "meta_id": f"wamid.backend{self.n}"}


@pytest.fixture
def fakes(monkeypatch):
    f = Fakes()
    monkeypatch.setattr(nw, "forward", f.fwd)
    monkeypatch.setattr(nw, "send_text", f.send)
    return f


@pytest.fixture
def client(pg_url, monkeypatch, fakes):
    _run(pg_url, "TRUNCATE wa_messages, wa_contacts", fetch=False)

    def maker():
        engine = create_async_engine(pg_url, poolclass=NullPool)
        return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def db_dep():
        async with maker()() as session:
            yield session

    monkeypatch.setenv("META_APP_SECRET", APP_SECRET)
    monkeypatch.setenv("WA_VERIFY_TOKEN", VERIFY)
    monkeypatch.setenv("NEXA_WA_FORWARD_SECRET", FORWARD)
    monkeypatch.setattr(ep, "SESSION_FACTORY", maker())
    nw.PER_NUMBER.hits.clear()
    ep.SERVICE_PER_IP.hits.clear()
    app_main.app.dependency_overrides[get_db] = db_dep
    yield TestClient(app_main.app)
    app_main.app.dependency_overrides.pop(get_db, None)


def _admin(monkeypatch, ok=True):
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=ok))


def _sign(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _envelope(messages=None, statuses=None, name="Ana Gómez", wa=WA) -> dict:
    value = {"messaging_product": "whatsapp", "metadata": {"display_phone_number": "573144798220", "phone_number_id": "1331771733361816"}}
    if messages is not None:
        value["contacts"] = [{"profile": {"name": name}, "wa_id": wa}]
        value["messages"] = messages
    if statuses is not None:
        value["statuses"] = statuses
    return {"object": "whatsapp_business_account", "entry": [{"id": "1757949478648212", "changes": [{"field": "messages", "value": value}]}]}


def _text(mid: str, body: str, wa=WA, ts: int | None = None) -> dict:
    return {"from": wa, "id": mid, "timestamp": str(ts or int(time.time())), "type": "text", "text": {"body": body}}


def _hook(c, payload: dict, secret: str = APP_SECRET):
    body = json.dumps(payload).encode()
    return c.post(f"{URL}/webhook", content=body, headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body, secret)})


def _outbound(c, body: dict, secret: str | None = FORWARD):
    headers = {"X-Nexa-Forward": secret} if secret is not None else {}
    return c.post(f"{URL}/outbound", json=body, headers=headers)


def _msgs(url):
    return _run(url, "SELECT meta_id, direction, msg_type, body, status, error, options FROM wa_messages ORDER BY created_at, meta_id")


def _contact(url, wa=WA):
    rows = _run(url, "SELECT * FROM wa_contacts WHERE wa_id = :wa", {"wa": wa})
    return rows[0] if rows else None


# ------------------------------------------------------------------ verificacion de Meta
def test_verificacion_get(client, monkeypatch):
    ok = client.get(f"{URL}/webhook", params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1158201444"})
    assert ok.status_code == 200 and ok.text == "1158201444"
    assert client.get(f"{URL}/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "1"}).status_code == 403
    assert client.get(f"{URL}/webhook", params={"hub.mode": "unsubscribe", "hub.verify_token": VERIFY, "hub.challenge": "1"}).status_code == 403
    monkeypatch.delenv("WA_VERIFY_TOKEN")
    assert client.get(f"{URL}/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"}).status_code == 503


# ------------------------------------------------------------------ firma
def test_firma_mala_401_y_no_guarda(client, pg_url, fakes):
    payload = _envelope([_text("wamid.A1", "Hola")])
    body = json.dumps(payload).encode()
    assert client.post(f"{URL}/webhook", content=body).status_code == 401, "sin firma"
    assert _hook(client, payload, secret="otra-clave").status_code == 401, "firma con otra clave"
    r = client.post(f"{URL}/webhook", content=body + b" ", headers={"X-Hub-Signature-256": _sign(body)})
    assert r.status_code == 401, "cuerpo alterado"
    assert APP_SECRET not in r.text
    assert _msgs(pg_url) == [] and fakes.forwarded == []


def test_sin_clave_de_app_503(client, monkeypatch):
    monkeypatch.delenv("META_APP_SECRET")
    assert _hook(client, _envelope([_text("wamid.A1", "Hola")])).status_code == 503


# ------------------------------------------------------------------ mensaje nuevo
def test_mensaje_nuevo_se_guarda_y_se_reenvia_con_historial(client, pg_url, fakes):
    r = _hook(client, _envelope([_text("wamid.N1", "Hola")]))
    assert r.status_code == 200 and r.json() == {"ok": True}
    c = _contact(pg_url)
    assert c["profile_name"] == "Ana Gómez" and c["stage"] == "nuevo" and c["last_preview"] == "Hola"
    assert c["first_message_at"] and c["last_inbound_at"]
    assert [m["meta_id"] for m in _msgs(pg_url)] == ["wamid.N1"]
    assert len(fakes.forwarded) == 1
    f = fakes.forwarded[0]
    assert f["mensaje"]["texto"] == "Hola" and f["mensaje"]["respondible"] is True
    assert f["contacto"]["wa_id"] == WA and f["contacto"]["etapa"] == "nuevo"
    assert f["contacto"]["console_url"].endswith(f"#nexa/{c['id']}")
    assert f["primer_mensaje"] is True
    assert [h["texto"] for h in f["historial"]] == ["Hola"]


def test_historial_maximo_20(client, pg_url, fakes):
    base = int(time.time()) - 100
    for i in range(25):
        nw.PER_NUMBER.hits.clear()  # aqui se prueba el historial, no el limite
        _hook(client, _envelope([_text(f"wamid.H{i:02d}", f"m{i}", ts=base + i)]))
    last = fakes.forwarded[-1]
    assert len(last["historial"]) == 20
    assert last["historial"][-1]["texto"] == "m24" and last["historial"][0]["texto"] == "m5"


def test_duplicado_no_se_procesa_dos_veces(client, pg_url, fakes):
    payload = _envelope([_text("wamid.D1", "Hola")])
    _hook(client, payload)
    _hook(client, payload)
    assert [m["meta_id"] for m in _msgs(pg_url)] == ["wamid.D1"]
    assert len(fakes.forwarded) == 1


def test_no_texto_se_reenvia_marcado_no_respondible(client, fakes):
    audio = {"from": WA, "id": "wamid.AU1", "timestamp": str(int(time.time())), "type": "audio", "audio": {"id": "media1", "mime_type": "audio/ogg"}}
    _hook(client, _envelope([audio]))
    assert fakes.forwarded[0]["mensaje"]["tipo"] == "audio"
    assert fakes.forwarded[0]["mensaje"]["respondible"] is False


def test_boton_y_lista_guardan_titulo_e_id(client, pg_url, fakes):
    btn = {"from": WA, "id": "wamid.B1", "timestamp": str(int(time.time())), "type": "interactive",
           "interactive": {"type": "button_reply", "button_reply": {"id": "cita|2026-10-29T10:00:00-05:00", "title": "Jue 29 oct 10:00 am"}}}
    lst = {"from": WA, "id": "wamid.L1", "timestamp": str(int(time.time())), "type": "interactive",
           "interactive": {"type": "list_reply", "list_reply": {"id": "negocio|bar", "title": "Bar"}}}
    _hook(client, _envelope([btn, lst]))
    assert [(f["mensaje"]["texto"], f["mensaje"]["reply_id"]) for f in fakes.forwarded] == [
        ("Jue 29 oct 10:00 am", "cita|2026-10-29T10:00:00-05:00"), ("Bar", "negocio|bar")]


# ------------------------------------------------------------------ estados de entrega
def test_estados_se_guardan_y_solo_avanzan(client, pg_url, fakes):
    _hook(client, _envelope([_text("wamid.S0", "Hola")]))
    assert _outbound(client, {"wa_id": WA, "mensajes": [{"meta_id": "wamid.OUT1", "tipo": "text", "texto": "Hola, soy Nexa", "estado": "sent"}]}).status_code == 200
    st = lambda s: {"id": "wamid.OUT1", "status": s, "timestamp": str(int(time.time())), "recipient_id": WA}  # noqa: E731
    _hook(client, _envelope(statuses=[st("delivered")]))
    _hook(client, _envelope(statuses=[st("read")]))
    _hook(client, _envelope(statuses=[st("delivered")]))  # tarde: no retrocede
    out = [m for m in _msgs(pg_url) if m["direction"] == "out"]
    assert [(m["meta_id"], m["status"], m["body"]) for m in out] == [("wamid.OUT1", "read", "Hola, soy Nexa")]
    assert len(fakes.forwarded) == 1, "los estados no se reenvian a n8n"


def test_estado_antes_del_registro_de_n8n_y_fallido(client, pg_url):
    _hook(client, _envelope([_text("wamid.S0", "Hola")]))
    _hook(client, _envelope(statuses=[{"id": "wamid.OUT9", "status": "delivered", "timestamp": "1", "recipient_id": WA}]))
    _outbound(client, {"wa_id": WA, "mensajes": [{"meta_id": "wamid.OUT9", "tipo": "buttons", "texto": "Elige", "opciones": ["A", "B"], "estado": "sent"}]})
    out = [m for m in _msgs(pg_url) if m["direction"] == "out"]
    assert [(m["meta_id"], m["msg_type"], m["body"], m["status"], m["options"]) for m in out] == [("wamid.OUT9", "buttons", "Elige", "delivered", ["A", "B"])]
    _hook(client, _envelope(statuses=[{"id": "wamid.OUT9", "status": "failed", "recipient_id": WA,
                                       "errors": [{"code": 131047, "title": "Re-engagement message"}]}]))
    out = [m for m in _msgs(pg_url) if m["direction"] == "out"]
    assert out[0]["status"] == "failed" and out[0]["error"].startswith("131047")


# ------------------------------------------------------------------ pausa, baja y limite
def test_pausado_guarda_pero_no_reenvia(client, pg_url, fakes):
    _hook(client, _envelope([_text("wamid.P1", "Hola")]))
    _run(pg_url, "UPDATE wa_contacts SET nexa_paused = true", fetch=False)
    _hook(client, _envelope([_text("wamid.P2", "¿Siguen ahí?")]))
    assert [m["meta_id"] for m in _msgs(pg_url)] == ["wamid.P1", "wamid.P2"]
    assert len(fakes.forwarded) == 1 and fakes.sent == []


@pytest.mark.parametrize("word", ["baja", "STOP", "No me escriban más", "por favor dejen de escribirme", "Unsubscribe"])
def test_baja_confirma_una_vez_y_luego_no_responde(client, pg_url, fakes, word):
    _hook(client, _envelope([_text("wamid.B1", word)]))
    c = _contact(pg_url)
    assert c["stage"] == "baja"
    assert fakes.forwarded == [], "la baja no pasa por Nexa"
    assert len(fakes.sent) == 1 and "te dimos de baja" in fakes.sent[0][1]
    _hook(client, _envelope([_text("wamid.B2", "hola otra vez")]))
    _hook(client, _envelope([_text("wamid.B3", "baja")]))
    assert len(fakes.sent) == 1 and fakes.forwarded == []
    out = [m for m in _msgs(pg_url) if m["direction"] == "out"]
    assert len(out) == 1 and out[0]["status"] == "sent"
    # Nexa (n8n) tampoco puede sacar a alguien de la baja
    _outbound(client, {"wa_id": WA, "etapa": "calificado"})
    assert _contact(pg_url)["stage"] == "baja"


def test_frases_que_no_son_baja():
    for t in ["Hola", "¿Cuánto bajan los costos?", "la bajada de precios", "stopper", "no me escribieron el correo"]:
        assert nw.is_opt_out(t) is False, t


def test_limite_20_por_minuto_por_numero(client, pg_url, fakes):
    base = int(time.time())
    for i in range(23):
        _hook(client, _envelope([_text(f"wamid.R{i:02d}", f"m{i}", ts=base)]))
    assert len(_msgs(pg_url)) == 23, "todo se guarda"
    assert len(fakes.forwarded) == 20, "solo 20 por minuto pasan a Nexa"
    _hook(client, _envelope([_text("wamid.OTRO", "hola", wa="573009998877")], wa="573009998877"))
    assert len(fakes.forwarded) == 21, "el limite es por numero"


def test_fuera_de_24_horas_no_se_responde(client, fakes):
    _hook(client, _envelope([_text("wamid.V1", "Hola", ts=int(time.time()) - 25 * 3600)]))
    assert fakes.forwarded == [] and fakes.sent == []


def test_n8n_caido_responde_ya_te_respondemos(client, pg_url, fakes):
    fakes.forward_ok = False
    _hook(client, _envelope([_text("wamid.F1", "Hola")]))
    assert fakes.sent == [(WA, "Ya te respondemos en un momento.")]
    assert [m["body"] for m in _msgs(pg_url) if m["direction"] == "out"] == ["Ya te respondemos en un momento."]


# ------------------------------------------------------------------ outbound
def test_outbound_exige_secreto(client):
    assert _outbound(client, {"wa_id": WA}, secret=None).status_code == 401
    assert _outbound(client, {"wa_id": WA}, secret="otro").status_code == 401


def test_outbound_sin_variable_503(client, monkeypatch):
    monkeypatch.delenv("NEXA_WA_FORWARD_SECRET")
    assert _outbound(client, {"wa_id": WA}).status_code == 503


def test_outbound_contacto_desconocido_404(client):
    assert _outbound(client, {"wa_id": "570000000000"}).status_code == 404


def test_outbound_guarda_y_actualiza_datos_y_etapa(client, pg_url):
    _hook(client, _envelope([_text("wamid.O1", "Hola, tengo un bar en Medellín")]))
    r = _outbound(client, {
        "wa_id": WA, "consentimiento_visto": True, "etapa": "calificado", "accion": "ninguna",
        "mensajes": [{"meta_id": "wamid.X1", "tipo": "text", "texto": "Hola, soy Nexa, asistente virtual con IA.", "estado": "sent"},
                     {"meta_id": "wamid.X2", "tipo": "list", "texto": "¿Qué tipo de negocio tienes?", "opciones": ["Restaurante", "Bar"], "estado": "sent"}],
        "datos_detectados": {"idioma": "es", "tipo_negocio": "Bar", "ciudad": "Medellín", "tamano": "12 mesas", "dolor": "pedidos",
                             "correo": "ana@bar.co"},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["contacto"]["etapa"] == "calificado" and body["etapa_label"] == "Calificado"
    assert body["contacto"]["console_url"].endswith(body["contacto"]["id"])
    c = _contact(pg_url)
    assert (c["business_type"], c["city"], c["size"], c["main_pain"], c["email"], c["language"]) == ("Bar", "Medellín", "12 mesas", "pedidos", "ana@bar.co", "es")
    assert c["consent_seen"] is True and c["last_preview"] == "¿Qué tipo de negocio tienes?"
    assert [m["meta_id"] for m in _msgs(pg_url) if m["direction"] == "out"] == ["wamid.X1", "wamid.X2"]
    # lo vacio no borra lo ya detectado; un correo invalido no se guarda; demo agendada no vuelve atras
    _outbound(client, {"wa_id": WA, "etapa": "demo_agendada", "datos_detectados": {"ciudad": "", "correo": "no-es-correo"},
                       "demo": {"inicio": "2026-10-29T10:00:00-05:00", "enlace": "https://meet.google.com/abc-defg-hij"}})
    _outbound(client, {"wa_id": WA, "etapa": "calificado"})
    c = _contact(pg_url)
    assert c["city"] == "Medellín" and c["email"] == "ana@bar.co" and c["stage"] == "demo_agendada"
    assert c["demo_link"] == "https://meet.google.com/abc-defg-hij" and c["demo_at"]


def test_outbound_valida_el_cuerpo(client):
    assert _outbound(client, {"wa_id": "abc"}).status_code == 422
    assert _outbound(client, {"wa_id": WA, "etapa": "inventada"}).status_code == 422
    assert _outbound(client, {"wa_id": WA, "mensajes": [{"tipo": "template", "texto": "x"}]}).status_code == 422


def test_resumen_diario(client, pg_url):
    _hook(client, _envelope([_text("wamid.Y1", "Hola")]))
    _outbound(client, {"wa_id": WA, "etapa": "demo_agendada"})
    assert client.get(f"{URL}/daily-summary").status_code == 401
    r = client.get(f"{URL}/daily-summary", headers={"X-Nexa-Forward": FORWARD})
    d = r.json()
    assert (d["nuevas"], d["calificadas"], d["demos"], d["personas"], d["activas"]) == (1, 1, 1, 0, 1)
    assert d["contactos"][0]["wa_id"] == WA


# ------------------------------------------------------------------ consola (Admin V2)
def test_consola_exige_admin_v2(client, monkeypatch):
    _admin(monkeypatch, ok=False)
    for path in ("/conversations", "/conversations/00000000-0000-4000-8000-000000000000",
                 "/conversations/00000000-0000-4000-8000-000000000000/export.csv"):
        assert client.get(ADMIN + path).status_code == 401, path
    assert client.post(f"{ADMIN}/conversations/00000000-0000-4000-8000-000000000000/pause", json={"paused": True}).status_code == 401
    assert client.post(f"{ADMIN}/conversations/00000000-0000-4000-8000-000000000000/not-interested").status_code == 401


def test_consola_lista_filtros_y_nuevas(client, pg_url, monkeypatch):
    _admin(monkeypatch)
    _hook(client, _envelope([_text("wamid.C1", "Hola")]))
    _hook(client, _envelope([_text("wamid.C2", "Buenas", wa="573005556677")], name="Bar La 70", wa="573005556677"))
    _outbound(client, {"wa_id": "573005556677", "etapa": "calificado", "datos_detectados": {"tipo_negocio": "Bar", "ciudad": "Cali"}})
    d = client.get(f"{ADMIN}/conversations").json()
    assert d["total"] == 2 and d["nuevas"] == 2
    assert d["counts"]["nuevo"] == 1 and d["counts"]["calificado"] == 1
    assert {i["nombre"] for i in d["items"]} == {"Ana Gómez", "Bar La 70"}
    assert all(i["nueva"] for i in d["items"])
    assert [i["nombre"] for i in client.get(f"{ADMIN}/conversations", params={"stage": "calificado"}).json()["items"]] == ["Bar La 70"]
    assert [i["nombre"] for i in client.get(f"{ADMIN}/conversations", params={"q": "cali"}).json()["items"]] == ["Bar La 70"]
    assert [i["nombre"] for i in client.get(f"{ADMIN}/conversations", params={"q": "300 111"}).json()["items"]] == ["Ana Gómez"]
    assert client.get(f"{ADMIN}/conversations", params={"q": "100%"}).json()["items"] == []
    assert client.get(f"{ADMIN}/conversations", params={"desde": "2001-01-01", "hasta": "2001-01-02"}).json()["items"] == []
    assert client.get(f"{ADMIN}/conversations", params={"stage": "x"}).status_code == 422
    assert client.get(f"{ADMIN}/conversations", params={"desde": "ayer"}).status_code == 422
    assert client.get(f"{ADMIN}/conversations").headers["cache-control"].startswith("no-store")


def test_consola_detalle_pausar_reanudar_no_interesado_y_csv(client, pg_url, monkeypatch, fakes):
    _admin(monkeypatch)
    _hook(client, _envelope([_text("wamid.E1", "=HYPERLINK(\"x\")")]))
    _outbound(client, {"wa_id": WA, "mensajes": [{"meta_id": "wamid.E2", "tipo": "buttons", "texto": "Elige un horario", "opciones": ["Jue 10:00 am"], "estado": "sent"}]})
    _hook(client, _envelope(statuses=[{"id": "wamid.E2", "status": "read", "recipient_id": WA}]))
    cid = _contact(pg_url)["id"]
    cid = str(cid)
    d = client.get(f"{ADMIN}/conversations/{cid}").json()
    assert [(m["direccion"], m["texto"]) for m in d["mensajes"]] == [("in", "=HYPERLINK(\"x\")"), ("out", "Elige un horario")]
    assert d["mensajes"][1]["opciones"] == ["Jue 10:00 am"] and d["mensajes"][1]["estado"] == "read"
    assert d["entregas"]["read"] == 1 and d["contacto"]["nombre"] == "Ana Gómez"
    assert client.get(f"{ADMIN}/conversations").json()["nuevas"] == 0, "abrirla la marca como vista"

    p = client.post(f"{ADMIN}/conversations/{cid}/pause", json={"paused": True}).json()
    assert p["contacto"]["nexa_pausada"] is True
    _hook(client, _envelope([_text("wamid.E3", "Hola?")]))
    assert len(fakes.forwarded) == 1, "pausada no reenvia"
    assert client.post(f"{ADMIN}/conversations/{cid}/pause", json={"paused": False}).json()["contacto"]["nexa_pausada"] is False
    _hook(client, _envelope([_text("wamid.E4", "Hola de nuevo")]))
    assert len(fakes.forwarded) == 2, "reanudada vuelve a reenviar"

    n = client.post(f"{ADMIN}/conversations/{cid}/not-interested").json()
    assert n["contacto"]["etapa"] == "no_interesado"

    r = client.get(f"{ADMIN}/conversations/{cid}/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert f'filename="nexa-{WA}.csv"' in r.headers["content-disposition"]
    body = r.content.decode("utf-8-sig")
    assert body.splitlines()[0] == "numero,nombre,negocio,ciudad,tamano,dolor,correo,etapa"
    assert f"{WA},Ana Gómez" in body and "no_interesado" in body
    assert "'=HYPERLINK" in body, "sin formulas en el CSV"
    assert "Elige un horario,Jue 10:00 am,read" in body

    assert client.get(f"{ADMIN}/conversations/no-es-uuid").status_code == 404
    assert client.get(f"{ADMIN}/conversations/00000000-0000-4000-8000-000000000000").status_code == 404
