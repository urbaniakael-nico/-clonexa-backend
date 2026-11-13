"""Bumeranes de la Cola de hoy: mp4 (y GIF) por nicho, solo con sesion de Admin V2.

401 sin sesion; con sesion se descargan como adjunto ("Guardar video"); tienda y transporte sin bumeran;
ninguna ruta estatica publica los sirve.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.web import admin_v2plus_routes as routes

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app_main.app)


@pytest.mark.parametrize("nicho", ["restaurante", "bar", "taller", "campo"])
def test_bumeran_solo_con_sesion(monkeypatch, nicho):
    monkeypatch.setattr(routes, "_active_session", AsyncMock(return_value=False))
    assert client.get(f"/admin-v2plus/bumeranes/{nicho}.mp4").status_code == 401
    assert client.get(f"/admin-v2plus/bumeranes/{nicho}.gif").status_code == 401
    monkeypatch.setattr(routes, "_active_session", AsyncMock(return_value=True))
    r = client.get(f"/admin-v2plus/bumeranes/{nicho}.mp4")
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
    assert r.headers["content-disposition"].startswith("attachment") and f"clonexa-{nicho}.mp4" in r.headers["content-disposition"]
    assert r.content[4:8] == b"ftyp" and len(r.content) < 600_000
    g = client.get(f"/admin-v2plus/bumeranes/{nicho}.gif")
    assert g.status_code == 200 and g.content[:6] == b"GIF89a" and len(g.content) <= 1_000_000


def test_tienda_y_transporte_sin_bumeran_y_nada_publico(monkeypatch):
    monkeypatch.setattr(routes, "_active_session", AsyncMock(return_value=True))
    for bad in ("tienda.mp4", "transporte.mp4", "bar.mov", "..%2Fadmin_v2plus.js.mp4"):
        assert client.get(f"/admin-v2plus/bumeranes/{bad}").status_code == 404, bad
    for path in ("/assets/bumeranes/bumeran-bar.mp4", "/admin-static/bumeranes/bumeran-bar.mp4", "/client-static/bumeranes/bumeran-bar.mp4",
                 "/client-static/bumeranes/bumeran-bar.gif"):
        assert client.get(path).status_code == 404, path
    files = sorted(p.name for p in (ROOT / "app" / "web" / "bumeranes").iterdir())
    assert files == [f"bumeran-{n}.{e}" for n in ("bar", "campo", "restaurante", "taller") for e in ("gif", "mp4")]
