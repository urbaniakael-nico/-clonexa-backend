"""n8n de TikTok: el callback pasa code+state al backend y vuelve a la consola; la vista previa de cada video
suma el boton "Publicar en TikTok" (registrar la pieza no publica); la vista previa dice la hora de la franja."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops" / "n8n"))
import nexa_v2_flows as npf  # noqa: E402

CRED = {"httpHeaderAuth": {"id": "x", "name": "Nexa backend"}}


def test_callback_pasa_code_y_state_al_backend_y_redirige():
    f = npf.flow_tiktok_callback(CRED)
    n = {x["name"]: x for x in f.nodes}
    assert n["Callback TikTok"]["parameters"]["path"] == "tiktok-callback"
    assert n["Callback TikTok"]["parameters"]["responseMode"] == "responseNode"
    http = n["Pasar al backend"]["parameters"]
    assert http["url"] == npf.BACKEND + "/api/v1/tiktok/n8n/callback" and http["method"] == "POST"
    assert "code" in http["jsonBody"] and "state" in http["jsonBody"]
    assert n["Pasar al backend"]["credentials"] == CRED
    assert n["Volver a la consola"]["parameters"]["respondWith"] == "redirect"
    blob = json.dumps(f.nodes)
    assert "client_secret" not in blob and "oauth/token" not in blob     # el canje lo hace el backend


def test_vista_previa_con_boton_publicar_en_tiktok():
    f = npf.flow_mostrar("s", CRED)
    n = {x["name"]: x for x in f.nodes}
    reg = n["TikTok: registrar pieza"]["parameters"]
    assert reg["url"] == npf.BACKEND + "/api/v1/tiktok/n8n/pieza" and reg["contentType"] == "multipart-form-data"
    assert reg["bodyParameters"]["parameters"][0] == {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "data"}
    rows = n["Texto y botones (TikTok)"]["parameters"]["inlineKeyboard"]["rows"]
    assert rows[1]["row"]["buttons"][0] == {"text": "🎵 Publicar en TikTok", "additionalFields": {"url": "={{ $json.enlace }}"}}
    # el video sale a Telegram y tambien se registra; sin enlace, el mensaje sale igual sin el boton
    assert [x["node"] for x in f.conns["Bajar video"]["main"][0]] == ["Enviar video", "TikTok: registrar pieza"]
    assert f.conns["¿Enlace de TikTok?"]["main"][1][0]["node"] == "Texto y botones"
    assert "Enviar video" not in f.conns or not f.conns["Enviar video"]["main"][0]
    # sin credencial (como antes): el mismo flujo de siempre
    old = npf.flow_mostrar("s")
    assert not any(x["name"] == "TikTok: registrar pieza" for x in old.nodes)


def test_vista_previa_dice_la_hora_de_la_franja():
    code = {x["name"]: x for x in npf.flow_mostrar("s", CRED).nodes}["Pieza"]["parameters"]["jsCode"]
    assert "'11:30 a. m.'" in code and "'7:00 p. m.'" in code and "a las ' + hora + '." in code
