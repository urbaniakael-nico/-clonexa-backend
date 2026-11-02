"""Nexa por WhatsApp contra Postgres REAL (pgserver) y la app completa.

- Webhook de Meta: verificacion GET, firma mala 401, sin variable 503, mensaje
  nuevo reenviado a n8n con contacto e historial, duplicado no se procesa dos
  veces, estados de entrega (solo avanzan; antes o despues del registro de n8n),
  pausado no reenvia, "baja" confirma una sola vez y despues no responde, limite
  de 20 por minuto por numero, n8n caido o lento (10 s) -> respuesta de respaldo
  de Nexa y aviso a Telegram (maximo 1 cada 15 min); error al guardar o al
  responder -> log + aviso; otro phone_number_id (muestra del panel) no se
  guarda; cada paso deja su linea en el log; el log de acceso tapa el token.
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
        self.alerts: list[str] = []
        self.forward_ok = True
        self.send_ok = True
        self.forward_delay = 0.0
        self.n = 0

    async def alert(self, text_: str) -> bool:
        self.alerts.append(text_)
        return True

    async def fwd(self, payload: dict) -> bool:
        self.forwarded.append(payload)
        if self.forward_delay:
            await asyncio.sleep(self.forward_delay)
        return self.forward_ok

    async def send(self, wa_id: str, body: str) -> dict:
        self.n += 1
        self.sent.append((wa_id, body))
        if not self.send_ok:
            return {"ok": False, "error": "400 131047 Re-engagement message"}
        return {"ok": True, "meta_id": f"wamid.backend{self.n}"}


@pytest.fixture
def fakes(monkeypatch):
    f = Fakes()
    monkeypatch.setattr(nw, "forward", f.fwd)
    monkeypatch.setattr(nw, "send_text", f.send)
    monkeypatch.setattr(nw, "_deliver_alert", f.alert)
    monkeypatch.setitem(nw.ALERT_STATE, "last", None)
    monkeypatch.setitem(nw.ALERT_STATE, "suppressed", 0)
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


RESPALDO = "¡Hola! Soy Nexa, la asistente virtual de Clonexa. En un momento te respondo."


def test_n8n_caido_responde_respaldo_y_avisa(client, pg_url, fakes):
    fakes.forward_ok = False
    _hook(client, _envelope([_text("wamid.F1", "Hola")]))
    assert fakes.sent == [(WA, RESPALDO)]
    assert [m["body"] for m in _msgs(pg_url) if m["direction"] == "out"] == [RESPALDO]
    assert len(fakes.alerts) == 1 and "n8n" in fakes.alerts[0]
    assert WA not in fakes.alerts[0] and WA[-4:] in fakes.alerts[0]  # el numero va tapado


def test_n8n_que_no_contesta_a_tiempo_igual_responde(client, pg_url, fakes, monkeypatch):
    monkeypatch.setattr(nw, "N8N_TIMEOUT", 0.2)
    fakes.forward_delay = 3.0
    started = time.monotonic()
    _hook(client, _envelope([_text("wamid.F2", "Hola")]))
    assert time.monotonic() - started < 2.5
    assert fakes.sent == [(WA, RESPALDO)]
    assert len(fakes.alerts) == 1


def test_forward_real_un_solo_intento_con_10_s(monkeypatch):
    calls = []

    class Slow:
        def __init__(self, *a, **k):
            calls.append(k.get("timeout"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            await asyncio.sleep(5)

    monkeypatch.setenv("NEXA_WA_FORWARD_SECRET", FORWARD)
    monkeypatch.setattr(nw, "N8N_TIMEOUT", 0.2)
    monkeypatch.setattr(nw.httpx, "AsyncClient", Slow)
    assert asyncio.run(nw.forward({"x": 1})) is False
    assert calls == [0.2]  # un solo intento, sin reintento que lo alargue
    assert "TimeoutError" in nw.LAST_FORWARD_ERROR["detail"] and FORWARD not in nw.LAST_FORWARD_ERROR["detail"]


def test_aviso_maximo_uno_cada_15_minutos(fakes):
    async def go():
        assert await nw.alert("fallo A", "x", at=1000.0) is True
        assert await nw.alert("fallo B", "x", at=1000.0 + 60) is False
        assert await nw.alert("fallo C", "x", at=1000.0 + 14 * 60) is False
        assert await nw.alert("fallo D", "x", at=1000.0 + 15 * 60 + 1) is True
    asyncio.run(go())
    assert len(fakes.alerts) == 2
    assert "fallo A" in fakes.alerts[0] and "fallo D" in fakes.alerts[1] and "+2 errores" in fakes.alerts[1]


def test_aviso_que_falla_no_tumba_nada(monkeypatch):
    async def boom(_t):
        raise RuntimeError("telegram caido")
    monkeypatch.setattr(nw, "_deliver_alert", boom)
    monkeypatch.setitem(nw.ALERT_STATE, "last", None)
    assert asyncio.run(nw.alert("x", "y")) is False


def test_error_al_guardar_queda_en_log_y_avisa(client, pg_url, fakes, monkeypatch, caplog):
    async def broken(*a, **k):
        raise RuntimeError("columna no existe")
    monkeypatch.setattr(nw, "insert_message", broken)
    caplog.set_level("INFO", logger="clonexa.nexa_wa")
    r = _hook(client, _envelope([_text("wamid.E1", "Hola")]))
    assert r.status_code == 200  # Meta no reintenta en bucle
    assert len(fakes.alerts) == 1 and "guardar" in fakes.alerts[0] and "RuntimeError" in fakes.alerts[0]
    assert any("nexa_wa ERROR" in rec.getMessage() for rec in caplog.records)
    assert fakes.forwarded == []


def test_error_en_un_mensaje_no_tumba_los_demas(client, pg_url, fakes, monkeypatch):
    original = nw.insert_message

    async def flaky(db, cid, **k):
        if k.get("meta_id") == "wamid.M1":
            raise RuntimeError("x")
        return await original(db, cid, **k)
    monkeypatch.setattr(nw, "insert_message", flaky)
    _hook(client, _envelope([_text("wamid.M1", "uno"), _text("wamid.M2", "dos")]))
    assert [m["meta_id"] for m in _msgs(pg_url)] == ["wamid.M2"]
    assert len(fakes.forwarded) == 1


def test_envio_fallido_avisa(client, pg_url, fakes):
    fakes.forward_ok = False
    fakes.send_ok = False
    _hook(client, _envelope([_text("wamid.S1", "Hola")]))
    assert [m["status"] for m in _msgs(pg_url) if m["direction"] == "out"] == ["failed"]
    assert len(fakes.alerts) == 1  # n8n + envio en la misma ventana: un solo aviso


def test_otro_numero_no_se_guarda(client, pg_url, fakes, caplog):
    caplog.set_level("INFO", logger="clonexa.nexa_wa")
    payload = _envelope([_text("wamid.P1", "this is a text message", wa="16315551181")])
    payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "123456123"
    assert _hook(client, payload).status_code == 200
    assert _contact(pg_url, "16315551181") is None and fakes.forwarded == []
    assert any("otro_numero" in rec.getMessage() for rec in caplog.records)


BSUID = "CO.1349120865530274191"


def _bsuid_envelope(mid: str, body: str) -> dict:
    """Forma real de produccion (2 nov 2026): sin telefono, con from_user_id y user_id."""
    msg = {"from_user_id": BSUID, "id": mid, "timestamp": str(int(time.time())), "type": "text", "text": {"body": body}}
    payload = _envelope([msg])
    payload["entry"][0]["changes"][0]["value"]["contacts"] = [{"profile": {"name": "Ana", "username": "ana.g"}, "user_id": BSUID}]
    return payload


def test_usuario_sin_telefono_bsuid_se_guarda_y_se_reenvia(client, pg_url, fakes):
    assert _hook(client, _bsuid_envelope("wamid.U1", "Hola")).status_code == 200
    c = _contact(pg_url, BSUID)
    assert c is not None and c["profile_name"] == "Ana"
    assert [m["meta_id"] for m in _msgs(pg_url)] == ["wamid.U1"]
    assert len(fakes.forwarded) == 1 and fakes.forwarded[0]["contacto"]["wa_id"] == BSUID
    assert fakes.alerts == []


def test_bsuid_n8n_caido_responde_respaldo(client, pg_url, fakes):
    fakes.forward_ok = False
    _hook(client, _bsuid_envelope("wamid.U2", "Hola"))
    assert fakes.sent == [(BSUID, RESPALDO)]


def test_outbound_acepta_bsuid(client, pg_url, fakes):
    _hook(client, _bsuid_envelope("wamid.U3", "Hola"))
    r = _outbound(client, {"wa_id": BSUID, "mensajes": [{"meta_id": "wamid.out.U3", "texto": "Hola, soy Nexa"}], "consentimiento_visto": True})
    assert r.status_code == 200 and r.json()["contacto"]["wa_id"] == BSUID
    assert _outbound(client, {"wa_id": "CO.x y", "mensajes": []}).status_code == 422


def test_send_text_usa_recipient_para_bsuid_y_to_para_telefono(monkeypatch):
    sent = []

    class Resp:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return {"messages": [{"id": "wamid.ok"}]}

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            sent.append(json)
            return Resp()

    monkeypatch.setenv("WA_TOKEN", "tok")
    monkeypatch.setattr(nw.httpx, "AsyncClient", Client)
    asyncio.run(nw.send_text(BSUID, "hola"))
    asyncio.run(nw.send_text(WA, "hola"))
    assert sent[0]["recipient"] == BSUID and "to" not in sent[0]
    assert sent[1]["to"] == WA and "recipient" not in sent[1]


def test_mensaje_sin_from_toma_el_numero_de_contacts(client, pg_url, fakes):
    msg = _text("wamid.C1", "Hola")
    msg.pop("from")
    assert _hook(client, _envelope([msg])).status_code == 200
    assert _contact(pg_url, WA) is not None
    assert [m["meta_id"] for m in _msgs(pg_url)] == ["wamid.C1"] and len(fakes.forwarded) == 1


def test_mensaje_sin_id_ni_numero_deja_la_forma_en_el_log_y_avisa(client, pg_url, fakes, caplog):
    caplog.set_level("INFO", logger="clonexa.nexa_wa")
    msg = _text("wamid.C2", "Hola secreto")
    msg.pop("from")
    msg.pop("id")
    payload = _envelope([msg])
    payload["entry"][0]["changes"][0]["value"]["contacts"] = [{"profile": {"name": "Ana"}, "user_id": "CO.123"}]
    _hook(client, payload)
    line = next(rec.getMessage() for rec in caplog.records if "mensaje_sin_id" in rec.getMessage())
    assert "id=no from=no" in line and "campos_mensaje=text,timestamp,type" in line and "campos_contacto=profile,user_id/profile:name" in line
    assert "Hola secreto" not in line and "CO.123" not in line and "Ana" not in line  # solo nombres de campos
    assert len(fakes.alerts) == 1 and _contact(pg_url, WA) is None


def test_cada_paso_queda_en_el_log_sin_secretos(client, pg_url, fakes, caplog):
    caplog.set_level("INFO", logger="clonexa.nexa_wa")
    _hook(client, _envelope([_text("wamid.L1", "Hola")]))
    text_ = "\n".join(rec.getMessage() for rec in caplog.records if rec.name == "clonexa.nexa_wa")
    for step in ("recibido", "firma_ok", "tipo object=whatsapp_business_account", "mensajes=1", "guardado", "reenviado_a_n8n", "resultado"):
        assert step in text_, step
    assert WA not in text_ and APP_SECRET not in text_ and FORWARD not in text_


def test_estados_quedan_en_el_log(client, caplog, fakes):
    caplog.set_level("INFO", logger="clonexa.nexa_wa")
    _hook(client, _envelope(statuses=[{"id": "wamid.X", "status": "delivered", "recipient_id": "573009999999", "timestamp": "1"}]))
    text_ = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "estados=1" in text_ and '"statuses": 0' in text_


def test_firma_mala_queda_en_el_log(client, caplog):
    caplog.set_level("INFO", logger="clonexa.nexa_wa")
    assert _hook(client, _envelope([_text("wamid.B1", "Hola")]), secret="otra").status_code == 401
    assert any("firma_mala" in rec.getMessage() for rec in caplog.records)


def test_log_de_acceso_tapa_el_token_de_verificacion():
    import logging
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', (
        "1.2.3.4:5", "GET", f"/api/v1/nexa-wa/webhook?hub.mode=subscribe&hub.verify_token={VERIFY}&hub.challenge=9&hub_verify_token={VERIFY}",
        "1.1", 200), None)
    assert ep.RedactVerifyToken().filter(rec) is True
    line = rec.getMessage()
    assert VERIFY not in line and "hub.verify_token=***" in line and "hub_verify_token=***" in line and "hub.challenge=9" in line
    assert any(isinstance(f, ep.RedactVerifyToken) for f in logging.getLogger("uvicorn.access").filters)


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
