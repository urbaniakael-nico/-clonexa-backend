"""Publicar en TikTok: 401 sin sesion, state firmado y de un solo uso, tokens cifrados y nunca en respuestas,
reglas de las Content Sharing Guidelines validadas en el servidor, creator_info antes de publicar, FILE_UPLOAD,
estado de la publicacion y borrador. TikTok y la base de datos son falsos (sin red)."""
from __future__ import annotations

import json
import struct
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.api.v1.endpoints import prospecting, social_metrics
from app.services import tiktok_posting as tt

client = TestClient(app_main.app)
BASE = "/api/v1/tiktok"
ACCESS, REFRESH = "act.SECRETO-access-token-1234567890", "rft.SECRETO-refresh-token-1234567890"


class MemStore:
    def __init__(self):
        self.states, self.account, self.pieces, self.posts = {}, None, {}, {}

    async def save_state(self, nonce):
        self.states[nonce] = {"t": datetime.now(timezone.utc), "used": False}

    async def use_state(self, nonce, max_age):
        s = self.states.get(nonce)
        if not s or s["used"] or (datetime.now(timezone.utc) - s["t"]).total_seconds() > max_age:
            return False
        s["used"] = True
        return True

    async def get_account(self):
        return self.account

    async def save_account(self, a):
        self.account = dict(a)

    async def delete_account(self):
        self.account = None

    async def add_piece(self, p):
        self.pieces[p["id"]] = {**p, "created_at": datetime.now(timezone.utc)}

    async def get_piece(self, i):
        return self.pieces.get(i)

    async def list_pieces(self, limit=30):
        return list(self.pieces.values())[:limit]

    async def add_post(self, p):
        self.posts[p["id"]] = {**p, "fail_reason": "", "post_id": "", "created_at": datetime.now(timezone.utc)}

    async def update_post(self, i, **f):
        self.posts[i].update(f)

    async def get_post(self, i):
        return self.posts.get(i)

    async def list_posts(self, limit=30):
        return list(self.posts.values())[:limit]


def mp4(seconds: int, size: int = 4000) -> bytes:
    """mp4 minimo: ftyp + moov/mvhd con la duracion."""
    ftyp = struct.pack(">I4s", 16, b"ftyp") + b"isom\x00\x00\x02\x00"
    mvhd_body = b"\x00\x00\x00\x00" + b"\x00" * 8 + struct.pack(">II", 1000, seconds * 1000) + b"\x00" * 80
    mvhd = struct.pack(">I4s", 8 + len(mvhd_body), b"mvhd") + mvhd_body
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    data = ftyp + moov
    return data + struct.pack(">I4s", max(8, size - len(data)), b"free") + b"\x00" * max(0, size - len(data) - 8)


CREATOR = {"creator_avatar_url": "https://p16.tiktokcdn.com/a.jpg", "creator_nickname": "Clonexa", "creator_username": "clonexxa",
           "privacy_level_options": ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"], "comment_disabled": False,
           "duet_disabled": True, "stitch_disabled": False, "max_video_post_duration_sec": 60}


class FakeTikTok:
    def __init__(self):
        self.calls, self.creator, self.creator_error, self.uploads, self.status = [], dict(CREATOR), "", [], "PUBLISH_COMPLETE"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path, request.content))
        ok = {"error": {"code": "ok", "message": ""}}
        if path == "/v2/oauth/token/":
            return httpx.Response(200, json={"access_token": ACCESS, "refresh_token": REFRESH, "open_id": "open-123456", "scope": tt.SCOPES,
                                             "expires_in": 86400, "refresh_expires_in": 31536000})
        if path == "/v2/oauth/revoke/":
            return httpx.Response(200, json={})
        if path.endswith("/creator_info/query/"):
            if self.creator_error:
                return httpx.Response(200, json={"data": {}, "error": {"code": self.creator_error, "message": "x"}})
            return httpx.Response(200, json={"data": self.creator, **ok})
        if path.endswith("/video/init/"):
            return httpx.Response(200, json={"data": {"publish_id": "v_pub_1", "upload_url": "https://open-upload.tiktokapis.com/video/?x=1"}, **ok})
        if path.endswith("/status/fetch/"):
            ids = ["7400000000000000001"] if self.status == "PUBLISH_COMPLETE" else []
            return httpx.Response(200, json={"data": {"status": self.status, "publicaly_available_post_id": ids, "fail_reason": ""}, **ok})
        if request.method == "PUT":
            self.uploads.append(request.headers.get("content-range"))
            return httpx.Response(201)
        if path.startswith("/webhook/nexa-archivo"):
            return httpx.Response(200, content=mp4(15))
        return httpx.Response(404)


@pytest.fixture()
def env(monkeypatch):
    store, fake, media = MemStore(), FakeTikTok(), {}
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "clave-de-prueba")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "secreto-de-prueba")
    monkeypatch.setenv("NEXA_INGEST_TOKEN", "token-n8n")
    monkeypatch.setattr(tt, "store_for", lambda db: store)
    monkeypatch.setattr(tt, "TRANSPORT", httpx.MockTransport(fake))
    monkeypatch.setattr(tt, "media_put", lambda k, d: media.__setitem__(k, d))
    monkeypatch.setattr(tt, "media_get", lambda k: media[k])
    monkeypatch.setattr(social_metrics.admin_v2_routes, "_active_session", AsyncMock(return_value=True))
    app_main.app.dependency_overrides[get_db] = lambda: None
    yield store, fake, media
    app_main.app.dependency_overrides.pop(get_db, None)


N8N = {"X-Nexa-Token": "token-n8n"}


def connect(store):
    url = client.post(f"{BASE}/admin/conectar").json()["url"]
    state = httpx.URL(url).params["state"]
    r = client.post(f"{BASE}/n8n/callback", json={"code": "codigo-ok", "state": state}, headers=N8N)
    return url, state, r


def test_sin_sesion_401(monkeypatch):
    monkeypatch.setattr(social_metrics.admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    app_main.app.dependency_overrides[get_db] = lambda: None
    try:
        for method, path in [("GET", "/admin/estado"), ("POST", "/admin/conectar"), ("GET", "/admin/creator"), ("GET", "/admin/piezas"),
                             ("POST", "/admin/publicar"), ("POST", "/admin/borrador"), ("GET", "/admin/publicaciones"), ("POST", "/admin/desconectar")]:
            assert client.request(method, BASE + path, json={}).status_code == 401, path
        assert client.post(f"{BASE}/n8n/callback", json={}).status_code in (401, 503)
    finally:
        app_main.app.dependency_overrides.pop(get_db, None)


def test_conectar_url_de_tiktok_con_state_firmado(env):
    url = client.post(f"{BASE}/admin/conectar").json()["url"]
    q = httpx.URL(url).params
    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/?")
    assert q["client_key"] == "clave-de-prueba" and q["response_type"] == "code"
    assert q["scope"] == "user.info.basic,video.upload,video.publish"
    assert q["redirect_uri"] == "https://main-production-54df.up.railway.app/webhook/tiktok-callback"
    assert "." in q["state"] and len(q["state"]) > 40


def test_callback_canjea_guarda_cifrado_y_el_state_es_de_un_solo_uso(env):
    store, fake, _ = env
    _, state, r = connect(store)
    assert r.json() == {"ok": True, "redirect": "https://testserver/admin-v2plus#tiktok?conectada=1"}
    acc = store.account
    assert acc["open_id"] == "open-123456"
    assert ACCESS not in json.dumps(acc, default=str) and REFRESH not in json.dumps(acc, default=str)   # cifrados
    assert tt.decrypt(acc["access_enc"]) == ACCESS
    # reusado -> rechazo; inventado -> rechazo
    again = client.post(f"{BASE}/n8n/callback", json={"code": "otro", "state": state}, headers=N8N).json()
    assert again["ok"] is False and "error=estado" in again["redirect"]
    forged = client.post(f"{BASE}/n8n/callback", json={"code": "x", "state": "abc.0000"}, headers=N8N).json()
    assert forged["ok"] is False and "error=estado" in forged["redirect"]
    # el estado nunca devuelve tokens
    est = client.get(f"{BASE}/admin/estado").text
    assert ACCESS not in est and REFRESH not in est and '"conectada":true' in est.replace(" ", "")


def test_refresco_automatico_del_token(env):
    store, fake, _ = env
    connect(store)
    store.account["access_expires"] = datetime.now(timezone.utc) + timedelta(minutes=1)
    client.get(f"{BASE}/admin/creator")
    grants = [c[2] for c in fake.calls if c[1] == "/v2/oauth/token/"]
    assert any(b"grant_type=refresh_token" in g for g in grants)
    assert store.account["access_expires"] > datetime.now(timezone.utc) + timedelta(hours=1)


def test_desconectar_revoca_y_borra(env):
    store, fake, _ = env
    connect(store)
    assert client.post(f"{BASE}/admin/desconectar").json()["ok"]
    assert store.account is None and any(c[1] == "/v2/oauth/revoke/" for c in fake.calls)


def test_creator_info_sin_tokens_y_error_bloquea(env):
    store, fake, _ = env
    connect(store)
    r = client.get(f"{BASE}/admin/creator").json()
    assert r["nickname"] == "Clonexa" and r["privacy_level_options"][-1] == "SELF_ONLY" and r["max_video_post_duration_sec"] == 60
    assert ACCESS not in json.dumps(r)
    fake.creator_error = "spam_risk_too_many_posts"
    bad = client.get(f"{BASE}/admin/creator")
    assert bad.status_code == 400 and "Intenta más tarde" in bad.json()["detail"]["mensaje"]


def _piece(store, seconds=15):
    import asyncio

    return asyncio.run(tt.save_piece(None, mp4(seconds), origen="subida", tema="Bumerán bar"))


def test_reglas_del_servidor(env):
    store, fake, _ = env
    connect(store)
    p = _piece(store)
    post = lambda **kw: client.post(f"{BASE}/admin/publicar", json={"pieza": p["id"], **kw})
    assert post().json()["detail"]["codigo"] == "privacy_required"                       # sin valor por defecto
    assert post(privacy_level="FOLLOWER_OF_CREATOR").json()["detail"]["codigo"] == "privacy_invalid"
    assert post(privacy_level="PUBLIC_TO_EVERYONE", disclosure=True).json()["detail"]["mensaje"] == \
        "You need to indicate if your content promotes yourself, a third party, or both."
    assert post(privacy_level="SELF_ONLY", disclosure=True, branded_content=True).json()["detail"]["mensaje"] == \
        "Branded content visibility cannot be set to private."
    assert post(privacy_level="SELF_ONLY", caption="x" * 2201).json()["detail"]["codigo"] == "caption_too_long"
    long = _piece(store, seconds=90)
    assert client.post(f"{BASE}/admin/publicar", json={"pieza": long["id"], "privacy_level": "SELF_ONLY"}).json()["detail"]["codigo"] == "too_long"
    assert not any(c[1].endswith("/video/init/") for c in fake.calls)                     # nada llego a TikTok


def test_publicar_file_upload_y_estado(env):
    store, fake, _ = env
    connect(store)
    p = _piece(store)
    r = client.post(f"{BASE}/admin/publicar", json={"pieza": p["id"], "privacy_level": "SELF_ONLY", "caption": "Tu bar, en vivo",
                                                   "allow_comment": True, "allow_duet": True, "allow_stitch": False}).json()
    assert r["ok"] and r["estado"] == "PROCESANDO" and r["publish_id"] == "v_pub_1"
    init = next(json.loads(c[2]) for c in fake.calls if c[1] == "/v2/post/publish/video/init/")
    assert init["source_info"]["source"] == "FILE_UPLOAD" and init["source_info"]["total_chunk_count"] == 1
    info = init["post_info"]
    assert info["privacy_level"] == "SELF_ONLY" and info["title"] == "Tu bar, en vivo"
    assert info["disable_comment"] is False and info["disable_duet"] is True and info["disable_stitch"] is True   # duet deshabilitado por la cuenta
    assert info["brand_content_toggle"] is False and info["brand_organic_toggle"] is False
    creator_i = next(i for i, c in enumerate(fake.calls) if c[1].endswith("/creator_info/query/"))
    init_i = next(i for i, c in enumerate(fake.calls) if c[1].endswith("/video/init/"))
    assert creator_i < init_i                                                              # creator_info antes de publicar
    assert fake.uploads == [f"bytes 0-{len(mp4(15)) - 1}/{len(mp4(15))}"]
    st = client.get(f"{BASE}/admin/publicaciones/{r['id']}/estado").json()
    assert st["estado"] == "PUBLICADO" and st["post_id"] == "7400000000000000001"
    reg = client.get(f"{BASE}/admin/publicaciones").json()["publicaciones"][0]
    assert reg["publish_id"] == "v_pub_1" and reg["estado"] == "PUBLICADO" and ACCESS not in json.dumps(reg)


def test_borrador_va_a_la_bandeja(env):
    store, fake, _ = env
    connect(store)
    p = _piece(store)
    r = client.post(f"{BASE}/admin/borrador", json={"pieza": p["id"]}).json()
    assert r["ok"] and r["modo"] == "borrador"
    init = next(json.loads(c[2]) for c in fake.calls if c[1] == "/v2/post/publish/inbox/video/init/")
    assert "post_info" not in init and init["source_info"]["source"] == "FILE_UPLOAD"


def test_n8n_registra_pieza_solo_desde_su_enlace_firmado(env):
    store, fake, media = env
    bad = client.post(f"{BASE}/n8n/pieza", json={"video_url": "https://evil.test/v.mp4"}, headers=N8N)
    assert bad.status_code == 400
    ok = client.post(f"{BASE}/n8n/pieza", headers=N8N, json={"video_url": "https://main-production-54df.up.railway.app/webhook/nexa-archivo?f=1&e=2&s=3",
                                                             "fila": 19, "fecha": "2026-11-17", "tema": "Tu restaurante", "caption": "Texto TT"}).json()
    assert ok["ok"] and ok["enlace"].endswith("/admin-v2plus#tiktok=" + ok["id"])
    piece = store.pieces[ok["id"]]
    assert piece["origen"] == "calendario" and round(piece["duration_sec"]) == 15
    assert not any(c[1].endswith("/video/init/") for c in fake.calls)                     # registrar no publica
    assert client.post(f"{BASE}/n8n/pieza", json={"video_url": "x"}).status_code in (401, 503)


def test_subir_mp4_y_vista_previa(env):
    store, _, _ = env
    data = mp4(10)
    r = client.post(f"{BASE}/admin/subir", files={"file": ("bumeran.mp4", data, "video/mp4")}, data={"caption": "Hola"}).json()
    assert r["ok"] and round(r["pieza"]["duracion"]) == 10
    v = client.get(f"{BASE}/admin/piezas/{r['pieza']['id']}/video")
    assert v.status_code == 200 and v.headers["content-type"] == "video/mp4" and v.content == data
    assert client.post(f"{BASE}/admin/subir", files={"file": ("x.mp4", b"no es video", "video/mp4")}).status_code == 400


def test_duracion_de_un_mp4_real():
    from pathlib import Path

    data = (Path(__file__).resolve().parents[1] / "app" / "web" / "bumeranes" / "bumeran-bar.mp4").read_bytes()
    assert 5 <= tt.mp4_duration(data) <= 7


def test_script_de_la_pantalla_exige_sesion(monkeypatch):
    from app.web import admin_v2plus_routes as routes

    monkeypatch.setattr(routes, "_active_session", AsyncMock(return_value=False))
    assert client.get("/admin-v2plus-tiktok.js").status_code == 401
    monkeypatch.setattr(routes, "_active_session", AsyncMock(return_value=True))
    r = client.get("/admin-v2plus-tiktok.js")
    assert r.status_code == 200 and "CxConsoleTikTok" in r.text
