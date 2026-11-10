"""Laminas de carrusel de Nexa (plan B) y su endpoint POST /api/v1/nexa-content/carousel.

- render: 6 o 7 laminas 1080x1350, nada se sale de la lamina ni de la zona segura, los bloques no se
  montan, el resaltado sale en el degradado de marca y los textos largos bajan de tamano hasta caber.
- endpoint: token de servicio (503 sin variable, 401 token mal), 422 con menos de 4 puntos, PNG validos.
"""
from __future__ import annotations

import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as app_main
from app.api.v1.endpoints import social_metrics as sm
from app.services import nexa_carousel as nc

TOKEN = "t" * 32

SPEC = {
    "portada": {"categoria": "Bares y discotecas", "titulo": "Tu bar vende bien… pero", "resaltado": "la plata no aparece",
                "subtitulo": "5 fugas de dinero que se esconden cada noche. ¿Cuántas tienes tú?"},
    "puntos": [
        {"titulo": "Botellas que salen sin registrar", "hoy": "El inventario se cuenta el lunes.", "con_clonexa": "Cada trago descuenta del inventario al venderse."},
        {"titulo": "Pedidos de palabra que no se cobran", "hoy": "“Tráeme otra” y nadie lo anota.", "con_clonexa": "El pedido llega por QR directo al barman."},
        {"titulo": "Mesas abiertas que se olvidan", "hoy": "La cuenta se cierra de memoria.", "con_clonexa": "Ves en vivo qué mesa sigue abierta."},
        {"titulo": "Cierre de caja a ojo", "hoy": "Más o menos cuadra.", "con_clonexa": "La caja cuadra con lo vendido en cada turno."},
        {"titulo": "Horas del personal en un cuaderno", "hoy": "Las horas se anotan a mano.", "con_clonexa": "Turnos y nómina en el celular."},
    ],
    "cierre": {"titulo": "Las 5 fugas, cerradas en", "resaltado": "un solo sistema", "texto": "Clonexa: pedidos, inventario, caja y personal."},
}

CONTENT = {"category", "title", "subtitle", "number", "box", "icon", "cta", "text"}


def _long_spec() -> dict:
    largo = ("Desarrollo internacionalización " * 10)
    return {
        "portada": {"categoria": "X" * 40, "titulo": largo[:90], "resaltado": largo[:60], "subtitulo": largo[:170]},
        "puntos": [{"titulo": largo[:90], "hoy": largo[:220], "con_clonexa": largo[:220]} for _ in range(5)],
        "cierre": {"titulo": largo[:70], "resaltado": largo[:50], "texto": largo[:180]},
    }


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _check(slides):
    for png, layout in slides:
        im = Image.open(io.BytesIO(png))
        assert im.size == (1080, 1350) and im.format == "PNG"
        for e in layout:
            x0, y0, x1, y1 = e["box"]
            assert nc.M - 4 <= x0 and x1 <= nc.W - nc.M + 1 and 0 <= y0 and y1 <= nc.H, e
        blocks = [e for e in layout if e["kind"] in CONTENT]
        for e in blocks:
            assert nc.TOP_SAFE <= e["box"][1] and e["box"][3] <= nc.BOTTOM_SAFE, e
        # los textos de dentro de un cuadro van dentro del cuadro; el resto no se monta
        top = [e for e in blocks if e["kind"] != "box_text"]
        for i, a in enumerate(top):
            for b in top[i + 1:]:
                assert not _overlap(a["box"], b["box"]), (a, b)


def test_siete_laminas_con_marca():
    slides = nc.render(SPEC)
    assert len(slides) == 7
    _check(slides)
    kinds = [[e["kind"] for e in lay] for _, lay in slides]
    assert "category" in kinds[0] and "number" in kinds[1] and "cta" in kinds[-1] and "icon" in kinds[-1]
    assert all({"logo", "counter", "dots", "footer"} <= set(k) for k in kinds)
    assert [len([e for e in lay if e["kind"] == "box"]) for _, lay in slides[1:-1]] == [2] * 5


def test_seis_laminas_con_cuatro_puntos():
    spec = dict(SPEC, puntos=SPEC["puntos"][:4])
    slides = nc.render(spec)
    assert len(slides) == 6
    _check(slides)


def test_textos_largos_caben():
    slides = nc.render(_long_spec())
    _check(slides)
    cover_title = next(e for e in slides[0][1] if e["kind"] == "title")
    assert cover_title["size"] < 96 and cover_title["lines"] <= 4


def test_resaltado_en_degradado():
    png, layout = nc.render(SPEC)[0]
    im = Image.open(io.BytesIO(png)).convert("RGB")
    x0, y0, x1, y1 = next(e for e in layout if e["kind"] == "title")["box"]
    reds = 0
    for x in range(x0, x1, 3):
        for y in range(y0, y1, 3):
            r, g, b = im.getpixel((x, y))
            if r > 220 and g < 90 and 40 < b < 140:
                reds += 1
    assert reds > 300


@pytest.fixture
def client(monkeypatch):
    sm.INGEST_PER_IP.hits.clear()
    return TestClient(app_main.app)


def test_endpoint_sin_variable_503(client, monkeypatch):
    monkeypatch.delenv("NEXA_INGEST_TOKEN", raising=False)
    r = client.post("/api/v1/nexa-content/carousel", json=SPEC, headers={"X-Nexa-Token": TOKEN})
    assert r.status_code == 503


def test_endpoint_token_mal_401(client, monkeypatch):
    monkeypatch.setenv("NEXA_INGEST_TOKEN", TOKEN)
    assert client.post("/api/v1/nexa-content/carousel", json=SPEC).status_code == 401
    assert client.post("/api/v1/nexa-content/carousel", json=SPEC, headers={"X-Nexa-Token": "otro"}).status_code == 401


def test_endpoint_valida_y_devuelve_png(client, monkeypatch):
    monkeypatch.setenv("NEXA_INGEST_TOKEN", TOKEN)
    h = {"X-Nexa-Token": TOKEN}
    bad = dict(SPEC, puntos=SPEC["puntos"][:3])
    assert client.post("/api/v1/nexa-content/carousel", json=bad, headers=h).status_code == 422
    r = client.post("/api/v1/nexa-content/carousel", json=SPEC, headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 7 and [s["name"] for s in data["slides"]] == [f"{i:02d}.png" for i in range(1, 8)]
    im = Image.open(io.BytesIO(base64.b64decode(data["slides"][0]["png_b64"])))
    assert im.size == (1080, 1350)


def test_ruta_con_guarda_visible():
    from fastapi.routing import APIRoute
    from app.services import console_catalog as cc

    by_path = {r.path: r for r in app_main.app.routes if isinstance(r, APIRoute)}
    assert cc._route_has_auth(by_path["/api/v1/nexa-content/carousel"])
