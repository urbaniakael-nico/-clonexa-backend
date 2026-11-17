"""Publicar en TikTok (@clonexxa) desde la consola v2+ (solo Admin V2), segun las Content Sharing Guidelines.

- Conectar: URL de autorizacion de TikTok con state firmado (HMAC) y de UN solo uso (10 min). El callback
  llega a n8n (webhook tiktok-callback, la redirect URI registrada), que pasa code+state al backend con la
  autenticacion de servicio; aqui se canjea el code y se guardan CIFRADOS (Fernet) access_token,
  refresh_token, expiraciones, scopes y open_id. Los tokens nunca salen en respuestas ni en logs.
- El access_token se renueva solo con el refresh_token (5 min antes de vencer). Desconectar revoca y borra.
- Publicar = accion explicita del usuario en la pantalla: creator_info SIEMPRE antes, reglas validadas aqui
  (privacidad dentro de privacy_level_options, interacciones deshabilitadas por la cuenta, divulgacion
  comercial, duracion maxima, caption <= 2200). Metodo FILE_UPLOAD (el backend sube el video); PULL_FROM_URL
  queda para cuando el prefijo de URL este verificado en la app.
- Borrador: video.upload a la bandeja de TikTok (inbox), sin post_info.
- Registro por publicacion: pieza, publish_id, estado, post_id, fecha (sin datos de otros usuarios).

Variables (Railway, backend): TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET. Opcional TIKTOK_REDIRECT_URI.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import struct
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from sqlalchemy import text

log = logging.getLogger("clonexa.tiktok")

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"
SCOPES = "user.info.basic,video.upload,video.publish"
DEFAULT_REDIRECT = "https://main-production-54df.up.railway.app/webhook/tiktok-callback"
STATE_SECONDS = 600
MAX_CAPTION = 2200
MAX_VIDEO_BYTES = 250 * 1024 * 1024
CHUNK = 10 * 1024 * 1024  # FILE_UPLOAD: un solo trozo hasta 64 MB; si no, trozos de 10 MB
ONE_CHUNK_MAX = 64 * 1024 * 1024
PRIVATE = "SELF_ONLY"
LEGAL = {
    "music": "https://www.tiktok.com/legal/page/global/music-usage-confirmation/en",
    "branded": "https://www.tiktok.com/legal/page/global/bc-policy/en",
}
# Errores de creator_info / init que significan "ahora no se puede publicar".
CANT_POST = {"spam_risk_too_many_posts", "spam_risk_user_banned_from_posting", "reached_active_user_cap", "spam_risk_too_many_pending_share"}


class TikTokError(Exception):
    def __init__(self, message: str, code: str = "", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


# ------------------------------------------------------------------ configuracion
def client_key() -> str:
    return os.getenv("TIKTOK_CLIENT_KEY", "").strip()


def _client_secret() -> str:
    return os.getenv("TIKTOK_CLIENT_SECRET", "").strip()


def redirect_uri() -> str:
    return os.getenv("TIKTOK_REDIRECT_URI", "").strip() or DEFAULT_REDIRECT


def configured() -> bool:
    return bool(client_key() and _client_secret())


def audited() -> bool:
    """Mientras TikTok no apruebe la auditoria de la app, solo se publica en privado (SELF_ONLY)."""
    return os.getenv("TIKTOK_APP_AUDITADA", "").strip().lower() in ("1", "true", "si", "sí")


def _master() -> bytes:
    from app.core.config import get_settings

    secret = get_settings().JWT_SECRET_KEY or "clonexa-local-secret"
    return hashlib.sha256(("clonexa-tiktok-v1:" + secret).encode("utf-8")).digest()


def _fernet():
    from cryptography.fernet import Fernet

    return Fernet(base64.urlsafe_b64encode(_master()))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")


# ------------------------------------------------------------------ almacenamiento
class SqlStore:
    """Tablas propias (sin datos de empresas clientes). Se crean al primer uso."""

    DDL = [
        """CREATE TABLE IF NOT EXISTS tiktok_oauth_states (nonce TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
           used_at TIMESTAMPTZ)""",
        """CREATE TABLE IF NOT EXISTS tiktok_account (id INT PRIMARY KEY DEFAULT 1, open_id TEXT NOT NULL, scope TEXT NOT NULL DEFAULT '',
           access_enc TEXT NOT NULL, refresh_enc TEXT NOT NULL, access_expires TIMESTAMPTZ NOT NULL, refresh_expires TIMESTAMPTZ NOT NULL,
           updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), CHECK (id = 1))""",
        """CREATE TABLE IF NOT EXISTS tiktok_pieces (id UUID PRIMARY KEY, origen TEXT NOT NULL, fila INT, fecha TEXT NOT NULL DEFAULT '',
           tema TEXT NOT NULL DEFAULT '', caption TEXT NOT NULL DEFAULT '', storage_key TEXT NOT NULL, size_bytes BIGINT NOT NULL,
           duration_sec REAL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        """CREATE TABLE IF NOT EXISTS tiktok_posts (id UUID PRIMARY KEY, piece_id UUID, modo TEXT NOT NULL, publish_id TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'PROCESANDO', fail_reason TEXT NOT NULL DEFAULT '', post_id TEXT NOT NULL DEFAULT '',
           privacy TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    ]
    _ready = False

    def __init__(self, db):
        self.db = db

    async def _ensure(self) -> None:
        if SqlStore._ready:
            return
        for ddl in self.DDL:
            await self.db.execute(text(ddl))
        await self.db.commit()
        SqlStore._ready = True

    async def _rows(self, sql: str, params: dict | None = None) -> list[dict]:
        await self._ensure()
        res = await self.db.execute(text(sql), params or {})
        try:
            return [dict(r) for r in res.mappings().all()]
        except Exception:
            return []

    async def _run(self, sql: str, params: dict | None = None) -> None:
        await self._ensure()
        await self.db.execute(text(sql), params or {})
        await self.db.commit()

    async def save_state(self, nonce: str) -> None:
        await self._run("DELETE FROM tiktok_oauth_states WHERE created_at < now() - interval '1 day'")
        await self._run("INSERT INTO tiktok_oauth_states (nonce) VALUES (:n)", {"n": nonce})

    async def use_state(self, nonce: str, max_age: int) -> bool:
        rows = await self._rows("""UPDATE tiktok_oauth_states SET used_at = now() WHERE nonce = :n AND used_at IS NULL
                                   AND created_at > now() - make_interval(secs => :a) RETURNING nonce""", {"n": nonce, "a": max_age})
        await self.db.commit()
        return bool(rows)

    async def get_account(self) -> Optional[dict]:
        rows = await self._rows("SELECT * FROM tiktok_account WHERE id = 1")
        return rows[0] if rows else None

    async def save_account(self, a: dict) -> None:
        await self._run("""INSERT INTO tiktok_account (id, open_id, scope, access_enc, refresh_enc, access_expires, refresh_expires, updated_at)
                           VALUES (1, :open_id, :scope, :access_enc, :refresh_enc, :access_expires, :refresh_expires, now())
                           ON CONFLICT (id) DO UPDATE SET open_id = EXCLUDED.open_id, scope = EXCLUDED.scope, access_enc = EXCLUDED.access_enc,
                             refresh_enc = EXCLUDED.refresh_enc, access_expires = EXCLUDED.access_expires,
                             refresh_expires = EXCLUDED.refresh_expires, updated_at = now()""", a)

    async def delete_account(self) -> None:
        await self._run("DELETE FROM tiktok_account WHERE id = 1")

    async def add_piece(self, p: dict) -> None:
        await self._run("""INSERT INTO tiktok_pieces (id, origen, fila, fecha, tema, caption, storage_key, size_bytes, duration_sec)
                           VALUES (CAST(:id AS uuid), :origen, :fila, :fecha, :tema, :caption, :storage_key, :size_bytes, :duration_sec)""", p)

    async def get_piece(self, piece_id: str) -> Optional[dict]:
        rows = await self._rows("SELECT * FROM tiktok_pieces WHERE id = CAST(:i AS uuid)", {"i": piece_id})
        return rows[0] if rows else None

    async def list_pieces(self, limit: int = 30) -> list[dict]:
        return await self._rows("SELECT * FROM tiktok_pieces ORDER BY created_at DESC LIMIT :n", {"n": limit})

    async def add_post(self, p: dict) -> None:
        await self._run("""INSERT INTO tiktok_posts (id, piece_id, modo, publish_id, status, privacy)
                           VALUES (CAST(:id AS uuid), CAST(:piece_id AS uuid), :modo, :publish_id, :status, :privacy)""", p)

    async def update_post(self, post_id: str, **fields) -> None:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        await self._run(f"UPDATE tiktok_posts SET {sets}, updated_at = now() WHERE id = CAST(:id AS uuid)", {"id": post_id, **fields})

    async def get_post(self, post_id: str) -> Optional[dict]:
        rows = await self._rows("SELECT * FROM tiktok_posts WHERE id = CAST(:i AS uuid)", {"i": post_id})
        return rows[0] if rows else None

    async def list_posts(self, limit: int = 30) -> list[dict]:
        return await self._rows("""SELECT p.*, COALESCE(x.tema, '') AS tema, COALESCE(x.fecha, '') AS fecha FROM tiktok_posts p
                                   LEFT JOIN tiktok_pieces x ON x.id = p.piece_id ORDER BY p.created_at DESC LIMIT :n""", {"n": limit})


def store_for(db) -> SqlStore:
    return SqlStore(db)


# ------------------------------------------------------------------ videos (bucket privado)
def media_put(key: str, data: bytes) -> None:
    from app.services import brand_media

    store = brand_media.backend()
    if isinstance(store, brand_media.S3Backend):
        store.put(key, data, content_type="video/mp4", private=True)
    else:
        store.put(key, data)


def media_get(key: str) -> bytes:
    from app.services import brand_media

    return brand_media.backend().get(key)


def mp4_duration(data: bytes) -> Optional[float]:
    """Duracion de un mp4 leyendo el atom mvhd (sin dependencias). None si no se puede leer."""
    def walk(buf: bytes, start: int, end: int):
        i = start
        while i + 8 <= end:
            size, kind = struct.unpack(">I4s", buf[i:i + 8])
            head = 8
            if size == 1 and i + 16 <= end:
                size = struct.unpack(">Q", buf[i + 8:i + 16])[0]
                head = 16
            elif size == 0:
                size = end - i
            if size < head:
                return None
            if kind == b"moov":
                return walk(buf, i + head, min(end, i + size))
            if kind == b"mvhd":
                body = buf[i + head:i + size]
                if not body:
                    return None
                if body[0] == 1:
                    scale, dur = struct.unpack(">IQ", body[20:32])
                else:
                    scale, dur = struct.unpack(">II", body[12:20])
                return dur / scale if scale else None
            i += size
        return None

    try:
        return walk(data, 0, len(data))
    except Exception:
        return None


async def save_piece(db, data: bytes, *, origen: str, fila: Optional[int] = None, fecha: str = "", tema: str = "", caption: str = "") -> dict:
    if not data or data[4:8] != b"ftyp":
        raise TikTokError("El archivo no es un video mp4.", "not_mp4")
    if len(data) > MAX_VIDEO_BYTES:
        raise TikTokError("El video pesa más de 250 MB.", "too_big")
    pid = str(uuid.uuid4())
    key = f"tiktok/{pid}.mp4"
    media_put(key, data)
    piece = {"id": pid, "origen": origen, "fila": fila, "fecha": fecha[:20], "tema": tema[:200], "caption": caption[:MAX_CAPTION],
             "storage_key": key, "size_bytes": len(data), "duration_sec": mp4_duration(data)}
    await store_for(db).add_piece(piece)
    return piece


def piece_view(p: dict) -> dict:
    return {"id": str(p["id"]), "origen": p["origen"], "fila": p.get("fila"), "fecha": p.get("fecha") or "", "tema": p.get("tema") or "",
            "caption": p.get("caption") or "", "duracion": p.get("duration_sec"), "tamano": p.get("size_bytes"),
            "creada": _iso(p.get("created_at"))}


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)


# ------------------------------------------------------------------ OAuth
def _sign(nonce: str) -> str:
    return hmac.new(_master(), ("state:" + nonce).encode("ascii"), hashlib.sha256).hexdigest()[:32]


async def new_state(db) -> str:
    nonce = secrets.token_urlsafe(24)
    await store_for(db).save_state(nonce)
    return f"{nonce}.{_sign(nonce)}"


async def consume_state(db, state: str) -> bool:
    """Valida la firma y lo marca usado (un solo uso, 10 minutos)."""
    nonce, _, mac = str(state or "").partition(".")
    if not nonce or not mac or not hmac.compare_digest(_sign(nonce), mac):
        return False
    return await store_for(db).use_state(nonce, STATE_SECONDS)


async def authorize_url(db) -> str:
    if not configured():
        raise TikTokError("Faltan TIKTOK_CLIENT_KEY y TIKTOK_CLIENT_SECRET en Railway.", "not_configured", 503)
    q = {"client_key": client_key(), "scope": SCOPES, "response_type": "code", "redirect_uri": redirect_uri(), "state": await new_state(db)}
    return AUTH_URL + "?" + urlencode(q)


def _client(transport=None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=60, transport=transport)


TRANSPORT = None  # las pruebas ponen aqui un httpx.MockTransport


def _api_error(body: Any, fallback: str) -> TikTokError:
    err = (body or {}).get("error") if isinstance(body, dict) else None
    if isinstance(err, dict) and err.get("code") and err.get("code") != "ok":
        return TikTokError(str(err.get("message") or fallback), str(err.get("code")))
    if isinstance(body, dict) and body.get("error") and isinstance(body.get("error"), str):  # errores del endpoint de tokens
        return TikTokError(str(body.get("error_description") or body.get("error")), str(body.get("error")))
    return TikTokError(fallback, "unknown")


async def _token_call(form: dict) -> dict:
    async with _client(TRANSPORT) as c:
        r = await c.post(f"{API}/oauth/token/", data={"client_key": client_key(), "client_secret": _client_secret(), **form},
                         headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"})
    body = _json(r)
    if r.status_code != 200 or not body.get("access_token"):
        raise _api_error(body, "TikTok no entregó el token.")
    return body


def _json(r: httpx.Response) -> dict:
    try:
        return r.json()
    except Exception:
        return {}


async def _save_tokens(db, body: dict) -> dict:
    now = datetime.now(timezone.utc)
    acc = {"open_id": str(body.get("open_id") or ""), "scope": str(body.get("scope") or ""),
           "access_enc": encrypt(body["access_token"]), "refresh_enc": encrypt(body.get("refresh_token") or ""),
           "access_expires": now + timedelta(seconds=int(body.get("expires_in") or 86400)),
           "refresh_expires": now + timedelta(seconds=int(body.get("refresh_expires_in") or 31536000))}
    await store_for(db).save_account(acc)
    return acc


async def exchange_code(db, code: str, state: str) -> dict:
    if not configured():
        raise TikTokError("Faltan TIKTOK_CLIENT_KEY y TIKTOK_CLIENT_SECRET en Railway.", "not_configured", 503)
    if not await consume_state(db, state):
        raise TikTokError("El enlace de conexión venció o ya se usó. Vuelve a tocar «Conectar TikTok».", "invalid_state", 400)
    if not code or len(code) > 2000:
        raise TikTokError("TikTok no envió el código de autorización.", "no_code")
    acc = await _save_tokens(db, await _token_call({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri()}))
    return {"open_id_fin": acc["open_id"][-4:], "scope": acc["scope"]}


async def access_token(db) -> str:
    """Token vigente; se renueva solo con el refresh_token si vence en menos de 5 minutos."""
    store = store_for(db)
    acc = await store.get_account()
    if not acc:
        raise TikTokError("La cuenta de TikTok no está conectada.", "not_connected", 409)
    now = datetime.now(timezone.utc)
    if acc["access_expires"] - now > timedelta(minutes=5):
        return decrypt(acc["access_enc"])
    if acc["refresh_expires"] <= now:
        raise TikTokError("La conexión con TikTok venció. Vuelve a conectar la cuenta.", "expired", 409)
    body = await _token_call({"grant_type": "refresh_token", "refresh_token": decrypt(acc["refresh_enc"])})
    await _save_tokens(db, body)
    return body["access_token"]


async def disconnect(db) -> None:
    store = store_for(db)
    acc = await store.get_account()
    if acc and configured():
        try:
            async with _client(TRANSPORT) as c:
                await c.post(f"{API}/oauth/revoke/", data={"client_key": client_key(), "client_secret": _client_secret(),
                                                          "token": decrypt(acc["access_enc"])},
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
        except Exception as exc:  # se borra igual; nunca se registra el token
            log.warning("TikTok: no se pudo revocar (%s); se borran los tokens igual", type(exc).__name__)
    await store.delete_account()


async def status(db) -> dict:
    acc = await store_for(db).get_account()
    return {"configurado": configured(), "auditada": audited(), "conectada": bool(acc), "metodo": "FILE_UPLOAD",
            "scopes": (acc or {}).get("scope", ""), "vence": _iso((acc or {}).get("refresh_expires")),
            "redirect_uri": redirect_uri()}


# ------------------------------------------------------------------ API de contenido
async def _post(db, path: str, payload: dict) -> dict:
    token = await access_token(db)
    async with _client(TRANSPORT) as c:
        r = await c.post(f"{API}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"})
    body = _json(r)
    err = body.get("error") if isinstance(body, dict) else None
    if r.status_code != 200 or (isinstance(err, dict) and err.get("code") not in (None, "", "ok")):
        e = _api_error(body, f"TikTok respondió {r.status_code}.")
        if e.code in CANT_POST:
            e.args = ("TikTok no deja publicar ahora en esta cuenta. Intenta más tarde.",)
        raise e
    return body.get("data") or {}


async def creator_info(db) -> dict:
    """Se consulta SIEMPRE al abrir la pantalla y antes de publicar. El avatar no se guarda (su URL vence en 2 h)."""
    d = await _post(db, "/post/publish/creator_info/query/", {})
    return {"avatar": d.get("creator_avatar_url") or "", "nickname": d.get("creator_nickname") or "", "username": d.get("creator_username") or "",
            "privacy_level_options": [str(x) for x in (d.get("privacy_level_options") or [])],
            "comment_disabled": bool(d.get("comment_disabled")), "duet_disabled": bool(d.get("duet_disabled")),
            "stitch_disabled": bool(d.get("stitch_disabled")), "max_video_post_duration_sec": int(d.get("max_video_post_duration_sec") or 0)}


def check_post(creator: dict, piece: dict, opts: dict) -> dict:
    """Reglas de las Content Sharing Guidelines (las mismas que la pantalla). Devuelve post_info o lanza TikTokError."""
    caption = str(opts.get("caption") or "")
    if len(caption) > MAX_CAPTION:
        raise TikTokError(f"El texto tiene más de {MAX_CAPTION} caracteres.", "caption_too_long")
    maxd = int(creator.get("max_video_post_duration_sec") or 0)
    dur = piece.get("duration_sec")
    if maxd and dur and dur > maxd + 0.5:
        raise TikTokError(f"El video dura {dur:.0f} s y esta cuenta permite máximo {maxd} s.", "too_long")
    privacy = str(opts.get("privacy_level") or "")
    if not privacy:
        raise TikTokError("Elige quién puede ver la publicación.", "privacy_required")
    if privacy not in creator.get("privacy_level_options", []):
        raise TikTokError("Esa privacidad no está disponible para esta cuenta.", "privacy_invalid")
    disclosure = bool(opts.get("disclosure"))
    your_brand = disclosure and bool(opts.get("your_brand"))
    branded = disclosure and bool(opts.get("branded_content"))
    if disclosure and not (your_brand or branded):
        raise TikTokError("You need to indicate if your content promotes yourself, a third party, or both.", "disclosure_incomplete")
    if branded and privacy == PRIVATE:
        raise TikTokError("Branded content visibility cannot be set to private.", "branded_private")
    allow = lambda k, off: bool(opts.get(k)) and not bool(creator.get(off))
    return {"title": caption, "privacy_level": privacy,
            "disable_comment": not allow("allow_comment", "comment_disabled"),
            "disable_duet": not allow("allow_duet", "duet_disabled"),
            "disable_stitch": not allow("allow_stitch", "stitch_disabled"),
            "brand_content_toggle": branded, "brand_organic_toggle": your_brand}


def _source(size: int) -> dict:
    if size <= ONE_CHUNK_MAX:
        return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    count = size // CHUNK  # el ultimo trozo lleva el sobrante (regla de TikTok)
    return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": CHUNK, "total_chunk_count": count}


async def _upload(url: str, data: bytes, src: dict) -> None:
    size, chunk, count = src["video_size"], src["chunk_size"], src["total_chunk_count"]
    async with _client(TRANSPORT) as c:
        for i in range(count):
            start = i * chunk
            end = size if i == count - 1 else start + chunk
            r = await c.put(url, content=data[start:end], headers={"Content-Type": "video/mp4", "Content-Length": str(end - start),
                                                                    "Content-Range": f"bytes {start}-{end - 1}/{size}"})
            if r.status_code not in (200, 201, 206):
                raise TikTokError(f"TikTok no recibió el video (parte {i + 1}: {r.status_code}).", "upload_failed")


async def publish(db, piece_id: str, opts: dict, *, draft: bool = False) -> dict:
    store = store_for(db)
    piece = await store.get_piece(piece_id)
    if not piece:
        raise TikTokError("Esa pieza no existe.", "no_piece", 404)
    data = media_get(piece["storage_key"])
    src = _source(len(data))
    if draft:
        d = await _post(db, "/post/publish/inbox/video/init/", {"source_info": src})
        privacy = ""
    else:
        creator = await creator_info(db)   # siempre antes de publicar
        post_info = check_post(creator, piece, opts)
        d = await _post(db, "/post/publish/video/init/", {"post_info": post_info, "source_info": src})
        privacy = post_info["privacy_level"]
    publish_id, upload_url = str(d.get("publish_id") or ""), str(d.get("upload_url") or "")
    if not publish_id or not upload_url:
        raise TikTokError("TikTok no devolvió dónde subir el video.", "no_upload_url")
    await _upload(upload_url, data, src)
    post = {"id": str(uuid.uuid4()), "piece_id": piece_id, "modo": "borrador" if draft else "directo", "publish_id": publish_id,
            "status": "PROCESANDO", "privacy": privacy}
    await store.add_post(post)
    return {"id": post["id"], "publish_id": publish_id, "estado": "PROCESANDO", "modo": post["modo"]}


STATUS_LABEL = {"PROCESSING_UPLOAD": "PROCESANDO", "PROCESSING_DOWNLOAD": "PROCESANDO", "SEND_TO_USER_INBOX": "EN_BANDEJA",
                "PUBLISH_COMPLETE": "PUBLICADO", "FAILED": "FALLO"}


async def post_status(db, post_id: str) -> dict:
    store = store_for(db)
    post = await store.get_post(post_id)
    if not post:
        raise TikTokError("Esa publicación no existe.", "no_post", 404)
    if post["status"] in ("PUBLICADO", "FALLO", "EN_BANDEJA") and (post["status"] != "PUBLICADO" or post.get("post_id")):
        return post_view(post)
    d = await _post(db, "/post/publish/status/fetch/", {"publish_id": post["publish_id"]})
    label = STATUS_LABEL.get(str(d.get("status") or ""), "PROCESANDO")
    ids = [str(x) for x in (d.get("publicaly_available_post_id") or d.get("publicly_available_post_id") or [])]
    fields = {"status": label, "fail_reason": str(d.get("fail_reason") or "")[:300], "post_id": ids[0] if ids else (post.get("post_id") or "")}
    await store.update_post(post_id, **fields)
    return post_view({**post, **fields})


def post_view(p: dict) -> dict:
    return {"id": str(p["id"]), "pieza": str(p.get("piece_id") or ""), "modo": p.get("modo"), "publish_id": p.get("publish_id"),
            "estado": p.get("status"), "motivo": p.get("fail_reason") or "", "post_id": p.get("post_id") or "", "privacidad": p.get("privacy") or "",
            "tema": p.get("tema") or "", "fecha": _iso(p.get("created_at"))}


def safe_message(exc: Exception) -> str:
    """Mensaje para la pantalla: nunca incluye tokens (los errores de TikTok no los traen; por si acaso se tapa)."""
    msg = str(exc) or "Error con TikTok."
    return re.sub(r"(act|rft)\.[A-Za-z0-9_\-!.]{10,}", "[oculto]", msg)[:300]
