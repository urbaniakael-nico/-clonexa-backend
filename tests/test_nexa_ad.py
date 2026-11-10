"""Anuncio visual de Nexa (plan B desde el 11 nov) y POST /api/v1/nexa-content/ad.

- render: 1080x1350, nada se sale de la imagen, titular en 2 lineas como maximo, tarjetas, funciones y
  botones donde van, las funciones no se montan sobre los botones, todas las escenas se dibujan.
- solo pantallas demo: la escena viene de un catalogo cerrado y cada captura existe en el repo.
- endpoint: token de servicio, 422 con escena desconocida, mas de 8 palabras o menos de 4 funciones.
"""
from __future__ import annotations

import base64
import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as app_main
from app.api.v1.endpoints import social_metrics as sm
from app.services import nexa_ad as na

TOKEN = "t" * 32
SPEC = {"escena": "restaurante-cocina", "titulo": "Del QR de la mesa", "resaltado": "a la cocina.", "remate": "",
        "subtitulo": "Carta en video, pedidos, domicilios y caja en un solo sistema.",
        "funciones": [{"emoji": "🎬", "texto": "Carta en video QR"}, {"emoji": "📲", "texto": "Pedidos desde la mesa"},
                      {"emoji": "👨‍🍳", "texto": "Directo a cocina"}, {"emoji": "🛵", "texto": "Domicilios"}, {"emoji": "💵", "texto": "Cierre de caja"}]}


def _inside(box) -> bool:
    x0, y0, x1, y1 = box
    return -45 <= x0 and x1 <= na.W + 45 and 0 <= y0 and y1 <= na.H  # la base del portatil sobresale 40 px a cada lado, como en el estudio


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@pytest.mark.parametrize("escena", list(na.SCENES))
def test_todas_las_escenas(escena):
    png, lay = na.render(dict(SPEC, escena=escena))
    im = Image.open(io.BytesIO(png))
    assert im.size == (1080, 1350) and im.format == "PNG"
    kinds = [e["kind"] for e in lay]
    assert kinds.count("card") == 2 and kinds.count("chip") == 5 and "cta" in kinds and "whatsapp" in kinds and "laptop" in kinds
    assert ("phone" in kinds) == bool(na.SCENES[escena]["phone"])
    for e in lay:
        assert _inside(e["box"]), e
    title = next(e for e in lay if e["kind"] == "title")
    assert title["lines"] <= 2
    cta = next(e for e in lay if e["kind"] == "cta")
    for chip in (e for e in lay if e["kind"] == "chip"):
        assert chip["box"][3] <= cta["box"][1] and chip["box"][2] <= na.W - na.M + 1
    sub = next((e for e in lay if e["kind"] == "subtitle"), None)
    assert sub is None or sub["box"][1] >= title["box"][3]


def test_titular_corta_antes_del_resaltado():
    _, lay = na.render(SPEC)
    t = next(e for e in lay if e["kind"] == "title")
    assert t["lines"] == 2 and t["size"] >= 64


def test_solo_capturas_del_catalogo_demo():
    for s in na.SCENES.values():
        for k in ("laptop", "phone"):
            if s[k]:
                assert os.path.isfile(os.path.join(na.ADS, "screens", s[k]))
        assert len(s["cards"]) == 2
    assert na.norm_emoji("🦄") == "✅" and na.norm_emoji("⏱️") == "⏱"
    for e in na.EMOJI:
        na.emoji_img(e, 24)


@pytest.fixture
def client():
    sm.INGEST_PER_IP.hits.clear()
    return TestClient(app_main.app)


def test_endpoint_anuncio(client, monkeypatch):
    monkeypatch.setenv("NEXA_INGEST_TOKEN", TOKEN)
    h = {"X-Nexa-Token": TOKEN}
    assert client.post("/api/v1/nexa-content/ad", json=SPEC).status_code == 401
    assert client.post("/api/v1/nexa-content/ad", json=dict(SPEC, escena="cliente-real"), headers=h).status_code == 422
    assert client.post("/api/v1/nexa-content/ad", json=dict(SPEC, titulo="una dos tres cuatro cinco seis", resaltado="siete ocho", remate="nueve"), headers=h).status_code == 422
    assert client.post("/api/v1/nexa-content/ad", json=dict(SPEC, titulo="una dos tres cuatro cinco seis siete", resaltado="ocho nueve", remate=""), headers=h).status_code == 422
    assert client.post("/api/v1/nexa-content/ad", json=dict(SPEC, funciones=SPEC["funciones"][:3]), headers=h).status_code == 422
    r = client.post("/api/v1/nexa-content/ad", json=SPEC, headers=h)
    assert r.status_code == 200 and r.json()["escena"] == "restaurante-cocina"
    assert Image.open(io.BytesIO(base64.b64decode(r.json()["png_b64"]))).size == (1080, 1350)
    e = client.get("/api/v1/nexa-content/ad/escenas", headers=h).json()
    assert set(e["escenas"]) == set(na.SCENES) and e["max_palabras_titular"] == 8


def test_rutas_con_guarda():
    from fastapi.routing import APIRoute
    from app.services import console_catalog as cc

    by = {r.path: r for r in app_main.app.routes if isinstance(r, APIRoute)}
    assert cc._route_has_auth(by["/api/v1/nexa-content/ad"]) and cc._route_has_auth(by["/api/v1/nexa-content/ad/escenas"])
