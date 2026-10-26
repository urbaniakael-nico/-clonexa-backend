"""Menu video (interruptor carta_video del modulo carta): datos, bucket,
cola de trabajos, cupo mensual, lectura de la carta y publicacion.

- Bytes de fotos y clips: SIEMPRE en el bucket clonexa-media (mismo cliente
  que el Estudio de marca), nunca en Postgres. Llaves con el company_id:
  menuvideo/{company_id}/{asset_id}.webp|.mp4 (publicas por /menu-media) y
  menuvideo-import/{company_id}/{import_id}/... (zona privada: la carta
  subida para leer; n8n la lee con una URL firmada de 15 min).
- dish_ref: id del plato de la Carta (portal y QR) o el id del plato en la
  tabla importada (consola, antes de publicar). Publicar copia lo del
  borrador al plato real.
- Cola simple en menu_media_jobs (en_cola, procesando, listo, error) con 2
  trabajadores por proceso: la peticion nunca espera al video.
- Cupo mensual (mes calendario de Bogota): gastan cupo crear un plato con su
  primera foto ("nuevo") y cambiar la foto de un plato que ya tenia
  ("cambio"). Precio, nombre, descripcion, opciones, agotado y orden no.
- Publicar = COMBINAR: crea lo que falta y actualiza lo que coincide por
  nombre normalizado dentro de su categoria; nunca borra.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import brand_media
from app.services import menu_media as mm

log = logging.getLogger("clonexa.menu_video")

FLAG = "carta_video"
MODULE = "carta"
QUOTA_NEW_KEY = "carta_video_quota_new"
QUOTA_CHANGES_KEY = "carta_video_quota_changes"
DEFAULT_QUOTA = 3
BOGOTA = ZoneInfo("America/Bogota")
TOKEN_ENV = "CARTA_IMPORT_TOKEN"
N8N_BASE = "https://main-production-54df.up.railway.app"
READ_WEBHOOK_ENV = "CARTA_N8N_READ_URL"
QUOTA_WEBHOOK_ENV = "CARTA_N8N_QUOTA_URL"
WORKERS = 2
SIGNED_SECONDS = 6 * 3600
JOB_STATES = ("en_cola", "procesando", "listo", "error")


class QuotaExceeded(Exception):
    def __init__(self, kind: str, state: dict):
        super().__init__(kind)
        self.kind = kind
        self.state = state


def _uuid(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise brand_media.ImageRejected("Identificador inválido.") from None


def _json(raw: Any, default: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default


def norm(value: Any) -> str:
    """"Ají de Gallina  (x2)" -> "aji de gallina x2" (para emparejar)."""
    plain = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in plain).split())


def clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def price_of(value: Any) -> Optional[float]:
    """"$ 12.500" / "12,500" / 12500 -> 12500.0 (pesos sin centavos en la carta)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
    else:
        raw = "".join(ch for ch in str(value) if ch.isdigit() or ch in ".,")
        if not raw:
            return None
        if "," in raw and "." in raw:
            raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
        elif raw.count(".") >= 1 and len(raw.rsplit(".", 1)[-1]) == 3:
            raw = raw.replace(".", "")
        elif raw.count(",") >= 1 and len(raw.rsplit(",", 1)[-1]) == 3:
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")
        try:
            number = float(Decimal(raw))
        except (InvalidOperation, ValueError):
            return None
    return number if 0 <= number < 100_000_000 else None


def month_key(now: Optional[datetime] = None) -> str:
    moment = (now or datetime.now(timezone.utc)).astimezone(BOGOTA)
    return f"{moment.year:04d}-{moment.month:02d}"


# ----------------------------------------------------------------- ajustes ---
async def carta_module(db: AsyncSession, company_id: Any) -> Optional[dict]:
    row = (await db.execute(text("""
        SELECT cm.enabled, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:c AS uuid) AND LOWER(m.code) = 'carta' LIMIT 1
    """), {"c": _uuid(company_id)})).mappings().first()
    if not row:
        return None
    return {"enabled": row.get("enabled") is True, "settings": _json(row.get("settings"), {}) or {}}


async def video_on(db: AsyncSession, company_id: Any) -> bool:
    try:
        async with db.begin_nested():  # savepoint: puede correr a mitad de un pedido
            module = await carta_module(db, company_id)
    except Exception as exc:  # sin poder leer: la carta de siempre
        log.warning("menu video: no se pudo leer el modulo carta: %s", type(exc).__name__)
        return False
    return bool(module and module["enabled"] and module["settings"].get(FLAG) is True)


def _limit(settings: dict, key: str) -> int:
    try:
        return max(0, min(999, int(settings.get(key, DEFAULT_QUOTA))))
    except (TypeError, ValueError):
        return DEFAULT_QUOTA


async def quota_state(db: AsyncSession, company_id: Any, now: Optional[datetime] = None) -> dict:
    module = await carta_module(db, company_id) or {"settings": {}}
    month = month_key(now)
    rows = (await db.execute(text("""
        SELECT kind, COUNT(*) AS n FROM menu_video_quota_log
        WHERE company_id = CAST(:c AS uuid) AND month = :m GROUP BY kind
    """), {"c": _uuid(company_id), "m": month})).mappings().all()
    used = {r["kind"]: int(r["n"]) for r in rows}

    def bucket(kind: str, key: str) -> dict:
        limit = _limit(module["settings"], key)
        return {"used": used.get(kind, 0), "limit": limit, "left": max(0, limit - used.get(kind, 0))}

    return {"month": month, "new": bucket("nuevo", QUOTA_NEW_KEY), "changes": bucket("cambio", QUOTA_CHANGES_KEY),
            "requests": used.get("solicitud", 0)}


async def spend(db: AsyncSession, company_id: Any, kind: str, item_id: Any, actor: str, now: Optional[datetime] = None) -> dict:
    """Gasta 1 de "nuevo" o "cambio" del mes (sin commit) o QuotaExceeded."""
    if kind not in ("nuevo", "cambio"):
        raise ValueError(kind)
    # un candado por empresa: dos pestañas a la vez no gastan de mas
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"menu_video_quota:{_uuid(company_id)}"})
    state = await quota_state(db, company_id, now)
    bucket = state["new" if kind == "nuevo" else "changes"]
    if bucket["left"] <= 0:
        raise QuotaExceeded(kind, state)
    await db.execute(text("""
        INSERT INTO menu_video_quota_log (company_id, month, kind, carta_item_id, actor, created_at)
        VALUES (CAST(:c AS uuid), :m, :k, CAST(:i AS uuid), :a, :t)
    """), {"c": _uuid(company_id), "m": state["month"], "k": kind, "i": _uuid(item_id), "a": clean(actor, 160),
           "t": now or datetime.now(timezone.utc)})
    bucket["used"] += 1
    bucket["left"] -= 1
    return state


async def log_request(db: AsyncSession, company_id: Any, detail: str, actor: str) -> None:
    await db.execute(text("""
        INSERT INTO menu_video_quota_log (company_id, month, kind, detail, actor) VALUES (CAST(:c AS uuid), :m, 'solicitud', :d, :a)
    """), {"c": _uuid(company_id), "m": month_key(), "d": clean(detail, 300), "a": clean(actor, 160)})


async def quota_log(db: AsyncSession, company_id: Any, limit: int = 60) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT q.month, q.kind, q.detail, q.actor, q.created_at, ci.name AS dish
        FROM menu_video_quota_log q LEFT JOIN carta_items ci ON ci.id = q.carta_item_id AND ci.company_id = q.company_id
        WHERE q.company_id = CAST(:c AS uuid) ORDER BY q.created_at DESC LIMIT :n
    """), {"c": _uuid(company_id), "n": limit})).mappings().all()
    return [{**dict(r), "created_at": r["created_at"].isoformat() if r.get("created_at") else None} for r in rows]


# ------------------------------------------------------------------ bucket ---
def asset_key(company_id: Any, asset_id: Any, ext: str) -> str:
    return f"menuvideo/{_uuid(company_id)}/{_uuid(asset_id)}.{ext}"


def _put(key: str, data: bytes, content_type: str, private: bool = False) -> None:
    store = brand_media.backend()
    if isinstance(store, brand_media.S3Backend):
        store.put(key, data, content_type=content_type, private=private)
    else:
        store.put(key, data)


def presign(key: str, seconds: int = 900) -> str:
    """URL firmada de solo lectura (n8n lee la carta subida, 15 min)."""
    store = brand_media.backend()
    if isinstance(store, brand_media.S3Backend):
        return store.client.generate_presigned_url("get_object", Params={"Bucket": store.bucket, "Key": key}, ExpiresIn=seconds)
    return f"memory://{key}"


def _sig_key() -> bytes:
    from app.web import admin_v2_routes as v2

    return hmac.new(v2._session_secret(), b"clonexa-menu-media-v1", hashlib.sha256).digest()


def sign(company_id: str, asset_id: str, expires: Optional[int] = None) -> str:
    exp = int(expires or time.time() + SIGNED_SECONDS)
    mac = hmac.new(_sig_key(), f"{company_id}.{asset_id}.{exp}".encode("ascii"), hashlib.sha256).hexdigest()[:32]
    return f"e={exp}&s={mac}"


def signature_ok(company_id: str, asset_id: str, exp: str, sig: str) -> bool:
    try:
        expires = int(exp)
    except (TypeError, ValueError):
        return False
    if expires < time.time():
        return False
    good = hmac.new(_sig_key(), f"{company_id}.{asset_id}.{expires}".encode("ascii"), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(good, str(sig or ""))


def media_url(company_id: str, asset_id: Optional[str], content_type: str = "image/webp", signed: bool = False) -> str:
    if not asset_id:
        return ""
    ext = "mp4" if content_type == "video/mp4" else "webp"
    url = f"/menu-media/{company_id}/{asset_id}.{ext}"
    return f"{url}?{sign(company_id, asset_id)}" if signed else url


async def store_asset(db: AsyncSession, company_id: Any, dish_ref: Any, role: str, variant: str, data: bytes,
                      content_type: str, width: Optional[int] = None, height: Optional[int] = None,
                      source_name: str = "", meta: Optional[dict] = None) -> str:
    cid = _uuid(company_id)
    asset_id = str(uuid.uuid4())
    key = asset_key(cid, asset_id, "mp4" if content_type == "video/mp4" else "webp")
    await asyncio.to_thread(_put, key, data, content_type)
    await db.execute(text("""
        INSERT INTO menu_media_assets (id, company_id, dish_ref, role, variant, storage_key, content_type, size_bytes,
                                       width, height, source_name, meta)
        VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(NULLIF(:d, '') AS uuid), :role, :variant, :key, :ct, :size,
                :w, :h, NULLIF(:src, ''), CAST(:meta AS jsonb))
    """), {"id": asset_id, "c": cid, "d": _uuid(dish_ref) if dish_ref else "", "role": role, "variant": variant,
           "key": key, "ct": content_type, "size": len(data), "w": width, "h": height, "src": clean(source_name, 200),
           "meta": json.dumps(meta or {}, ensure_ascii=False)})
    return asset_id


async def asset(db: AsyncSession, company_id: Any, asset_id: Any) -> Optional[dict]:
    try:
        cid, aid = _uuid(company_id), _uuid(asset_id)
    except brand_media.ImageRejected:
        return None
    row = (await db.execute(text("""
        SELECT id::text AS id, company_id::text AS company_id, dish_ref::text AS dish_ref, role, variant, storage_key,
               content_type, size_bytes, width, height, source_name, meta
        FROM menu_media_assets WHERE id = CAST(:a AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"a": aid, "c": cid})).mappings().first()
    return dict(row) if row else None


async def is_public(db: AsyncSession, company_id: Any, asset_id: Any) -> bool:
    """Publica = la usa hoy un plato real de la Carta de ESA empresa."""
    row = (await db.execute(text("""
        SELECT 1 FROM menu_dish_media dm JOIN carta_items ci ON ci.id = dm.dish_ref AND ci.company_id = dm.company_id
        WHERE dm.company_id = CAST(:c AS uuid)
          AND CAST(:a AS uuid) IN (dm.front_original, dm.front_remaster, dm.side_original, dm.side_remaster, dm.clip_asset, dm.poster_asset)
        LIMIT 1
    """), {"c": _uuid(company_id), "a": _uuid(asset_id)})).first()
    return bool(row)


async def read_bytes(row: dict) -> bytes:
    return await asyncio.to_thread(brand_media.backend().get, row["storage_key"])


async def discard(db: AsyncSession, company_id: Any, asset_ids: list) -> None:
    """Borra assets que ya nadie usa (bucket + fila). Nunca rompe la accion."""
    ids = [str(a) for a in asset_ids if a]
    if not ids:
        return
    cid = _uuid(company_id)
    still = (await db.execute(text("""
        SELECT unnest(ARRAY[front_original, front_remaster, side_original, side_remaster, clip_asset, poster_asset])::text AS a
        FROM menu_dish_media WHERE company_id = CAST(:c AS uuid)
    """), {"c": cid})).mappings().all()
    used = {r["a"] for r in still if r.get("a")}
    gone = [a for a in ids if a not in used]
    if not gone:
        return
    rows = (await db.execute(text("""
        SELECT id::text AS id, storage_key FROM menu_media_assets
        WHERE company_id = CAST(:c AS uuid) AND id::text = ANY(:ids)
    """), {"c": cid, "ids": gone})).mappings().all()
    try:
        await asyncio.to_thread(brand_media.backend().delete, [r["storage_key"] for r in rows])
    except Exception as exc:
        log.warning("menu video: no se pudo borrar del bucket: %s", type(exc).__name__)
    await db.execute(text("DELETE FROM menu_media_assets WHERE company_id = CAST(:c AS uuid) AND id::text = ANY(:ids)"),
                     {"c": cid, "ids": gone})


# ------------------------------------------------------- media por plato ---
MEDIA_COLUMNS = ("front_original", "front_remaster", "side_original", "side_remaster", "clip_asset", "poster_asset")


async def dish_media(db: AsyncSession, company_id: Any, dish_ref: Any) -> Optional[dict]:
    row = (await db.execute(text("""
        SELECT dish_ref::text AS dish_ref, front_original::text AS front_original, front_remaster::text AS front_remaster,
               side_original::text AS side_original, side_remaster::text AS side_remaster, use_remaster,
               clip_asset::text AS clip_asset, poster_asset::text AS poster_asset, clip_style, status, updated_at
        FROM menu_dish_media WHERE company_id = CAST(:c AS uuid) AND dish_ref = CAST(:d AS uuid)
    """), {"c": _uuid(company_id), "d": _uuid(dish_ref)})).mappings().first()
    return dict(row) if row else None


async def upsert_media(db: AsyncSession, company_id: Any, dish_ref: Any, **values: Any) -> None:
    allowed = {*MEDIA_COLUMNS, "use_remaster", "clip_style", "status"}
    sets = {k: v for k, v in values.items() if k in allowed}
    cid, ref = _uuid(company_id), _uuid(dish_ref)
    await db.execute(text("""
        INSERT INTO menu_dish_media (company_id, dish_ref) VALUES (CAST(:c AS uuid), CAST(:d AS uuid))
        ON CONFLICT (company_id, dish_ref) DO NOTHING
    """), {"c": cid, "d": ref})
    if not sets:
        return
    parts = []
    params: dict[str, Any] = {"c": cid, "d": ref}
    for key, value in sets.items():
        if key in MEDIA_COLUMNS:
            parts.append(f"{key} = CAST(NULLIF(:{key}, '') AS uuid)")
            params[key] = str(value or "")
        else:
            parts.append(f"{key} = :{key}")
            params[key] = value
    await db.execute(text(f"""
        UPDATE menu_dish_media SET {", ".join(parts)}, updated_at = now()
        WHERE company_id = CAST(:c AS uuid) AND dish_ref = CAST(:d AS uuid)
    """), params)


def chosen_photo(media: dict, role: str = "front") -> Optional[str]:
    remaster, original = media.get(f"{role}_remaster"), media.get(f"{role}_original")
    return (remaster if media.get("use_remaster", True) and remaster else None) or original


def media_payload(company_id: str, media: Optional[dict], signed: bool = False, video: bool = True) -> dict:
    """Lo que necesitan la consola, el portal y el QR (URLs, nunca llaves)."""
    if not media:
        return {"has_photo": False, "photo_url": "", "side_url": "", "video_url": "", "poster_url": "", "status": "sin_foto"}
    url = lambda a, ct="image/webp": media_url(company_id, a, ct, signed)  # noqa: E731
    out = {
        "has_photo": bool(media.get("front_original")),
        "photo_url": url(chosen_photo(media, "front")), "side_url": url(chosen_photo(media, "side")),
        "front_original_url": url(media.get("front_original")), "front_remaster_url": url(media.get("front_remaster")),
        "side_original_url": url(media.get("side_original")), "side_remaster_url": url(media.get("side_remaster")),
        "use_remaster": bool(media.get("use_remaster", True)), "clip_style": media.get("clip_style") or "",
        "status": media.get("status") or ("listo" if media.get("clip_asset") else "sin_video"),
        "video_url": "", "poster_url": "",
    }
    if video:
        out["video_url"] = url(media.get("clip_asset"), "video/mp4")
        out["poster_url"] = url(media.get("poster_asset"))
    return out


async def media_map(db: AsyncSession, company_id: Any, signed: bool = False, video: bool = True) -> dict[str, dict]:
    cid = _uuid(company_id)
    try:
        async with db.begin_nested():  # savepoint: nunca deshace lo pendiente de quien llama
            rows = (await db.execute(text("""
                SELECT dish_ref::text AS dish_ref, front_original::text AS front_original, front_remaster::text AS front_remaster,
                       side_original::text AS side_original, side_remaster::text AS side_remaster, use_remaster,
                       clip_asset::text AS clip_asset, poster_asset::text AS poster_asset, clip_style, status
                FROM menu_dish_media WHERE company_id = CAST(:c AS uuid)
            """), {"c": cid})).mappings().all()
    except Exception as exc:  # tabla aun sin migrar: sin fotos, la carta de siempre
        log.warning("menu video: sin tabla de media: %s", type(exc).__name__)
        return {}
    return {r["dish_ref"]: media_payload(cid, dict(r), signed, video) for r in rows}


# ------------------------------------------------------------------- fotos ---
async def save_photo(db: AsyncSession, company_id: Any, dish_ref: Any, role: str, raw: bytes, source_name: str = "",
                     meta: Optional[dict] = None) -> str:
    """Guarda la ORIGINAL (normalizada, sin metadatos) y la deja asignada al
    plato. La remasterizada y el clip los hace la cola."""
    image = await asyncio.to_thread(mm.load, raw)
    data, width, height = await asyncio.to_thread(mm.normalize, image)
    asset_id = await store_asset(db, company_id, dish_ref, role, "original", data, "image/webp", width, height, source_name, meta)
    current = await dish_media(db, company_id, dish_ref) or {}
    stale = [current.get(f"{role}_original"), current.get(f"{role}_remaster")]
    if role == "front":
        stale += [current.get("clip_asset"), current.get("poster_asset")]
    changes: dict[str, Any] = {f"{role}_original": asset_id, f"{role}_remaster": ""}
    if role == "front":
        changes.update(clip_asset="", poster_asset="", status="sin_video")
    await upsert_media(db, company_id, dish_ref, **changes)
    await discard(db, company_id, stale)
    return asset_id


async def assign_photo(db: AsyncSession, company_id: Any, asset_id: Any, dish_ref: Any, role: str) -> None:
    """Reasigna a mano una foto ya subida (consola, paso 3)."""
    row = await asset(db, company_id, asset_id)
    if not row or row["variant"] != "original":
        raise brand_media.ImageRejected("Esa foto no existe en esta empresa.")
    old_ref = row.get("dish_ref")
    if old_ref:
        old = await dish_media(db, company_id, old_ref) or {}
        for column in ("front_original", "side_original"):
            if old.get(column) == row["id"]:
                await upsert_media(db, company_id, old_ref, **{column: "", column.replace("original", "remaster"): ""})
    current = await dish_media(db, company_id, dish_ref) or {}
    stale = current.get(f"{role}_original")
    await db.execute(text("""
        UPDATE menu_media_assets SET dish_ref = CAST(:d AS uuid), role = :r WHERE id = CAST(:a AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"d": _uuid(dish_ref), "r": role, "a": row["id"], "c": _uuid(company_id)})
    await upsert_media(db, company_id, dish_ref, **{f"{role}_original": row["id"], f"{role}_remaster": ""})
    if stale and stale != row["id"]:
        await db.execute(text("UPDATE menu_media_assets SET dish_ref = NULL WHERE id = CAST(:a AS uuid) AND company_id = CAST(:c AS uuid)"),
                         {"a": stale, "c": _uuid(company_id)})


async def remove_photos(db: AsyncSession, company_id: Any, dish_ref: Any) -> None:
    current = await dish_media(db, company_id, dish_ref)
    if not current:
        return
    await db.execute(text("DELETE FROM menu_dish_media WHERE company_id = CAST(:c AS uuid) AND dish_ref = CAST(:d AS uuid)"),
                     {"c": _uuid(company_id), "d": _uuid(dish_ref)})
    await discard(db, company_id, [current.get(c) for c in MEDIA_COLUMNS])


# ------------------------------------------------------------------- cola ---
async def enqueue(db: AsyncSession, company_id: Any, dish_ref: Any, style: str = "auto") -> str:
    style = style if style in (*mm.STYLES, "auto") else "auto"
    cid, ref = _uuid(company_id), _uuid(dish_ref)
    waiting = (await db.execute(text("""
        SELECT id::text AS id FROM menu_media_jobs WHERE company_id = CAST(:c AS uuid) AND dish_ref = CAST(:d AS uuid) AND status = 'en_cola'
        ORDER BY created_at LIMIT 1
    """), {"c": cid, "d": ref})).mappings().first()
    if waiting:
        await db.execute(text("UPDATE menu_media_jobs SET style = :s WHERE id = CAST(:j AS uuid)"), {"s": style, "j": waiting["id"]})
        job_id = waiting["id"]
    else:
        job_id = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO menu_media_jobs (id, company_id, dish_ref, style) VALUES (CAST(:j AS uuid), CAST(:c AS uuid), CAST(:d AS uuid), :s)
        """), {"j": job_id, "c": cid, "d": ref, "s": style})
    await upsert_media(db, cid, ref, status="en_cola")
    return job_id


async def jobs_for(db: AsyncSession, company_id: Any, dish_refs: Optional[list] = None) -> dict[str, dict]:
    """Ultimo trabajo de cada plato."""
    rows = (await db.execute(text("""
        SELECT DISTINCT ON (dish_ref) id::text AS id, dish_ref::text AS dish_ref, style, status, error, result, created_at, finished_at
        FROM menu_media_jobs WHERE company_id = CAST(:c AS uuid)
        ORDER BY dish_ref, created_at DESC
    """), {"c": _uuid(company_id)})).mappings().all()
    wanted = {str(r) for r in dish_refs} if dish_refs else None
    out = {}
    for r in rows:
        if wanted is not None and r["dish_ref"] not in wanted:
            continue
        out[r["dish_ref"]] = {"id": r["id"], "style": r["style"], "status": r["status"], "error": r["error"] or "",
                              "result": _json(r["result"], {})}
    return out


async def claim(db: AsyncSession) -> Optional[dict]:
    row = (await db.execute(text("""
        UPDATE menu_media_jobs SET status = 'procesando', started_at = now(), attempts = attempts + 1
        WHERE id = (SELECT id FROM menu_media_jobs WHERE status = 'en_cola' ORDER BY created_at
                    FOR UPDATE SKIP LOCKED LIMIT 1)
        RETURNING id::text AS id, company_id::text AS company_id, dish_ref::text AS dish_ref, style
    """))).mappings().first()
    await db.commit()
    return dict(row) if row else None


async def _photo_image(db: AsyncSession, company_id: str, asset_id: Optional[str]):
    if not asset_id:
        return None
    row = await asset(db, company_id, asset_id)
    if not row:
        return None
    return await asyncio.to_thread(mm.load, await read_bytes(row))


async def process(db: AsyncSession, job: dict) -> dict:
    """Remasteriza lo que falte y arma el clip. Devuelve el resultado; los
    errores quedan en el trabajo (nunca tumban al trabajador)."""
    cid, ref = job["company_id"], job["dish_ref"]
    started = time.perf_counter()
    media = await dish_media(db, cid, ref)
    if not media or not media.get("front_original"):
        raise mm.MediaRejected("El plato no tiene foto de frente.")
    timings: dict[str, Any] = {}
    images: dict[str, Any] = {}
    for role in ("front", "side"):
        original_id = media.get(f"{role}_original")
        if not original_id:
            continue
        original = await _photo_image(db, cid, original_id)
        if original is None:
            raise mm.MediaRejected("No se encontró la foto original.")
        if not media.get(f"{role}_remaster"):
            t0 = time.perf_counter()
            result = await asyncio.to_thread(mm.remaster, original)
            timings[f"{role}_remaster_ms"] = round((time.perf_counter() - t0) * 1000)
            remaster_id = await store_asset(db, cid, ref, role, "remaster", result.data, "image/webp", result.width, result.height)
            await upsert_media(db, cid, ref, **{f"{role}_remaster": remaster_id})
            media[f"{role}_remaster"] = remaster_id
        images[role] = await asyncio.to_thread(mm.clip_source, original, bool(media.get("use_remaster", True)))
    clip = await asyncio.to_thread(mm.make_clip, images["front"], images.get("side"), job.get("style") or "auto")
    clip_id = await store_asset(db, cid, ref, "front", "clip", clip.video, "video/mp4", mm.CLIP_W, mm.CLIP_H,
                                meta={"style": clip.style, "attempts": clip.attempts})
    poster_id = await store_asset(db, cid, ref, "front", "poster", clip.poster, "image/webp", mm.CLIP_W, mm.CLIP_H)
    stale = [media.get("clip_asset"), media.get("poster_asset")]
    await upsert_media(db, cid, ref, clip_asset=clip_id, poster_asset=poster_id, clip_style=clip.style, status="listo")
    await discard(db, cid, stale)
    return {**timings, "clip_ms": clip.encode_ms, "total_ms": round((time.perf_counter() - started) * 1000),
            "clip_bytes": len(clip.video), "poster_bytes": len(clip.poster), "style": clip.style, "ffmpeg": mm.ffmpeg_version()}


async def run_job(db: AsyncSession, job: dict) -> dict:
    try:
        result = await process(db, job)
        await db.execute(text("""
            UPDATE menu_media_jobs SET status = 'listo', error = NULL, result = CAST(:r AS jsonb), finished_at = now()
            WHERE id = CAST(:j AS uuid)
        """), {"r": json.dumps(result), "j": job["id"]})
        await db.commit()
        return {"status": "listo", **result}
    except (mm.MediaRejected, mm.MediaUnavailable, brand_media.StorageUnavailable, brand_media.ImageRejected) as error:
        message = str(error)[:300]
    except Exception as error:  # pragma: no cover - defensa
        log.exception("menu video: trabajo %s fallo", job.get("id"))
        message = f"Error inesperado ({type(error).__name__})."
    await db.rollback()
    await db.execute(text("""
        UPDATE menu_media_jobs SET status = 'error', error = :e, finished_at = now() WHERE id = CAST(:j AS uuid)
    """), {"e": message, "j": job["id"]})
    await upsert_media(db, job["company_id"], job["dish_ref"], status="error")
    await db.commit()
    return {"status": "error", "error": message}


async def requeue_stale(db: AsyncSession) -> int:
    result = await db.execute(text("""
        UPDATE menu_media_jobs SET status = 'en_cola' WHERE status = 'procesando' AND started_at < now() - interval '10 minutes'
          AND attempts < 3
    """))
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


_wakeup: Optional[asyncio.Event] = None


def wake() -> None:
    if _wakeup is not None:
        _wakeup.set()


async def _worker(index: int) -> None:
    from app.core.database import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                if index == 0:
                    await requeue_stale(db)
                job = await claim(db)
                if job:
                    await run_job(db, job)
                    continue
        except Exception as exc:  # nunca tumba el servidor
            log.warning("menu video: trabajador %s: %s", index, type(exc).__name__)
        try:
            assert _wakeup is not None
            await asyncio.wait_for(_wakeup.wait(), timeout=5)
            _wakeup.clear()
        except asyncio.TimeoutError:
            pass


def start_workers() -> None:
    global _wakeup
    _wakeup = asyncio.Event()
    loop = asyncio.get_event_loop()
    for index in range(WORKERS):
        loop.create_task(_worker(index))
    log.info("menu video: %s trabajadores; ffmpeg %s", WORKERS, mm.ffmpeg_version() or "NO INSTALADO")


# ---------------------------------------------------------------- lectura ---
def clean_table(data: Any) -> dict:
    """La carta leida (o editada a mano) en una forma unica y limpia. Cada
    plato lleva su `ref` (id estable para fotos y clips antes de publicar)."""
    data = data if isinstance(data, dict) else {}
    categories: list[dict] = []
    seen: dict[str, dict] = {}

    def category(name: str, sub: str = "") -> None:
        key = norm(name)
        if not key:
            return
        if key not in seen:
            seen[key] = {"nombre": clean(name, 80).upper(), "subcategorias": []}
            categories.append(seen[key])
        if sub and norm(sub) not in {norm(s["nombre"]) for s in seen[key]["subcategorias"]}:
            seen[key]["subcategorias"].append({"nombre": clean(sub, 80).upper()})

    for cat in data.get("categorias") or []:
        if isinstance(cat, dict):
            category(cat.get("nombre"))
            for sub in cat.get("subcategorias") or []:
                if isinstance(sub, dict):
                    category(cat.get("nombre"), sub.get("nombre"))
    dishes = []
    for dish in data.get("platos") or []:
        if not isinstance(dish, dict) or not clean(dish.get("nombre"), 220):
            continue
        cat = clean(dish.get("categoria"), 80) or "OTROS"
        sub = clean(dish.get("subcategoria"), 80)
        category(cat, sub)
        try:
            ref = str(uuid.UUID(str(dish.get("ref"))))
        except (ValueError, TypeError, AttributeError):
            ref = str(uuid.uuid4())
        options = dish.get("opciones")
        if isinstance(options, list):
            options = ", ".join(clean(o if not isinstance(o, dict) else (o.get("nombre") or ""), 80) for o in options if o)
        dishes.append({"ref": ref, "categoria": cat.upper(), "subcategoria": sub.upper(), "nombre": clean(dish.get("nombre"), 220),
                       "descripcion": clean(dish.get("descripcion"), 500), "precio": price_of(dish.get("precio")),
                       "opciones": clean(options, 300)})
        if len(dishes) >= 400:
            break
    return {"categorias": categories[:60], "platos": dishes}


async def create_import(db: AsyncSession, company_id: Any, source: str, files: list[dict], status: str = "leyendo") -> str:
    import_id = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO menu_video_imports (id, company_id, status, source, files, table_data)
        VALUES (CAST(:i AS uuid), CAST(:c AS uuid), :s, :src, CAST(:f AS jsonb), CAST(:t AS jsonb))
    """), {"i": import_id, "c": _uuid(company_id), "s": status, "src": source, "f": json.dumps(files),
           "t": json.dumps({"categorias": [], "platos": []})})
    return import_id


async def get_import(db: AsyncSession, company_id: Any, import_id: Any) -> Optional[dict]:
    try:
        iid = _uuid(import_id)
    except brand_media.ImageRejected:
        return None
    row = (await db.execute(text("""
        SELECT id::text AS id, company_id::text AS company_id, status, source, files, table_data, error, summary,
               created_at, updated_at, read_at, published_at
        FROM menu_video_imports WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"i": iid, "c": _uuid(company_id)})).mappings().first()
    if not row:
        return None
    out = dict(row)
    out["files"] = _json(out["files"], [])
    out["table_data"] = _json(out["table_data"], {})
    out["summary"] = _json(out["summary"], {})
    for k in ("created_at", "updated_at", "read_at", "published_at"):
        out[k] = out[k].isoformat() if out.get(k) else None
    return out


async def latest_import(db: AsyncSession, company_id: Any) -> Optional[dict]:
    row = (await db.execute(text("""
        SELECT id::text AS id FROM menu_video_imports WHERE company_id = CAST(:c AS uuid) ORDER BY created_at DESC LIMIT 1
    """), {"c": _uuid(company_id)})).mappings().first()
    return await get_import(db, company_id, row["id"]) if row else None


async def save_table(db: AsyncSession, company_id: Any, import_id: Any, table: Any, status: Optional[str] = None,
                     error: Optional[str] = None) -> dict:
    cleaned = clean_table(table)
    await db.execute(text("""
        UPDATE menu_video_imports SET table_data = CAST(:t AS jsonb), status = COALESCE(CAST(:s AS varchar), status),
               error = CAST(:e AS varchar), read_at = CASE WHEN CAST(:s AS varchar) = 'lista' THEN now() ELSE read_at END,
               updated_at = now()
        WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"t": json.dumps(cleaned, ensure_ascii=False), "s": status, "e": error, "i": _uuid(import_id), "c": _uuid(company_id)})
    return cleaned


async def mark_import(db: AsyncSession, company_id: Any, import_id: Any, status: str, error: Optional[str] = None) -> None:
    await db.execute(text("""
        UPDATE menu_video_imports SET status = :s, error = CAST(:e AS varchar), updated_at = now() WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"s": status, "e": (error or None) and clean(error, 400), "i": _uuid(import_id), "c": _uuid(company_id)})


def read_webhook_url() -> str:
    return os.getenv(READ_WEBHOOK_ENV, "").strip() or f"{N8N_BASE}/webhook/clonexa-leer-carta"


def quota_webhook_url() -> str:
    return os.getenv(QUOTA_WEBHOOK_ENV, "").strip() or f"{N8N_BASE}/webhook/clonexa-aviso-cupo"


def token() -> str:
    return os.getenv(TOKEN_ENV, "").strip()


async def call_n8n(url: str, payload: dict, timeout: float = 20.0) -> tuple[bool, str]:
    """POST al webhook de n8n con X-Carta-Token. (ok, detalle sin secretos)."""
    secret = token()
    if not secret:
        return False, "Falta la variable CARTA_IMPORT_TOKEN en el servidor."
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers={"X-Carta-Token": secret})
    except Exception as error:
        return False, f"n8n no respondió ({type(error).__name__})."
    if response.status_code >= 300:
        return False, f"n8n respondió {response.status_code}."
    return True, ""


def match_photo(filename: str, dishes: list[dict]) -> tuple[Optional[str], str]:
    """Empareja una foto con su plato por el nombre del archivo:
    "lomo-saltado-perfil.jpg" -> (ref de "Lomo saltado", "side").
    Devuelve (None, rol) si ninguno se parece lo suficiente."""
    stem = norm(os.path.splitext(os.path.basename(str(filename or "")))[0])
    words = stem.split()
    side_words = {"perfil", "lado", "lateral", "side", "costado"}
    front_words = {"frente", "front", "frontal", "arriba", "top"}
    role = "side" if any(w in side_words for w in words) or (len(words) > 1 and words[-1] == "2") else "front"
    noise = side_words | front_words | {"foto", "img", "image", "imagen", "dsc", "copy", "copia", "final", "1", "2", "plato"}
    tokens = [w for w in words if w not in noise and not w.isdigit()]
    if not tokens:
        return None, role
    joined = " ".join(tokens)
    best, best_score = None, 0.0
    for dish in dishes:
        name = norm(dish.get("nombre"))
        if not name:
            continue
        if name == joined:
            return dish["ref"], role
        name_tokens = set(name.split())
        overlap = len(name_tokens & set(tokens))
        score = overlap / max(len(name_tokens | set(tokens)), 1)
        if score > best_score:
            best, best_score = dish["ref"], score
    return (best, role) if best_score >= 0.5 else (None, role)


# --------------------------------------------------------------- publicar ---
async def _categories(db: AsyncSession, company_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, parent_id::text AS parent_id, label, position FROM carta_categories
        WHERE company_id = CAST(:c AS uuid) ORDER BY position, lower(label)
    """), {"c": company_id})).mappings().all()
    return [dict(r) for r in rows]


async def _dishes(db: AsyncSession, company_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, name, price, category_id::text AS category_id, description FROM carta_items
        WHERE company_id = CAST(:c AS uuid)
    """), {"c": company_id})).mappings().all()
    return [dict(r) for r in rows]


def _top_of(category_id: Optional[str], by_id: dict[str, dict]) -> tuple[Optional[dict], Optional[dict]]:
    leaf = by_id.get(str(category_id or ""))
    if not leaf:
        return None, None
    if leaf.get("parent_id") and by_id.get(leaf["parent_id"]):
        return by_id[leaf["parent_id"]], leaf
    return leaf, None


def describe(dish: dict) -> str:
    text_value = clean(dish.get("descripcion"), 500)
    options = clean(dish.get("opciones"), 300)
    if options:
        text_value = f"{text_value} · Opciones: {options}" if text_value else f"Opciones: {options}"
    return text_value[:600]


async def plan_publish(db: AsyncSession, company_id: Any, table: dict) -> dict:
    """Que hara Publicar: platos nuevos, actualizados y sin cambios. Nunca borra."""
    cid = _uuid(company_id)
    table = clean_table(table)
    categories = await _categories(db, cid)
    by_id = {c["id"]: c for c in categories}
    existing: dict[tuple[str, str], dict] = {}
    for dish in await _dishes(db, cid):
        top, _sub = _top_of(dish.get("category_id"), by_id)
        existing.setdefault((norm(top["label"]) if top else "", norm(dish["name"])), dish)
    tops = {norm(c["label"]) for c in categories if not c.get("parent_id")}
    medias = await media_map(db, cid)
    plan: dict[str, Any] = {"new": [], "updated": [], "unchanged": [], "deleted": 0,
                            "new_categories": sorted({d["categoria"] for d in table["platos"] if norm(d["categoria"]) not in tops})}
    for dish in table["platos"]:
        match = existing.get((norm(dish["categoria"]), norm(dish["nombre"])))
        has_media = bool((medias.get(dish["ref"]) or {}).get("has_photo"))
        entry = {"ref": dish["ref"], "nombre": dish["nombre"], "categoria": dish["categoria"], "precio": dish["precio"],
                 "media": has_media}
        if not match:
            plan["new"].append(entry)
            continue
        changes = []
        if dish["precio"] is not None and float(match.get("price") or 0) != float(dish["precio"]):
            changes.append("precio")
        if describe(dish) and describe(dish) != (match.get("description") or ""):
            changes.append("descripción")
        if has_media:
            changes.append("foto/video")
        (plan["updated"] if changes else plan["unchanged"]).append({**entry, "id": match["id"], "changes": changes})
    plan["counts"] = {"new": len(plan["new"]), "updated": len(plan["updated"]), "unchanged": len(plan["unchanged"]), "deleted": 0}
    return plan


async def _ensure_category(db: AsyncSession, cid: str, categories: list[dict], label: str, parent_id: Optional[str]) -> str:
    for c in categories:
        if (c.get("parent_id") or None) == parent_id and norm(c["label"]) == norm(label):
            return c["id"]
    new_id = str(uuid.uuid4())
    siblings = [c for c in categories if (c.get("parent_id") or None) == parent_id]
    position = max([int(c.get("position") or 0) for c in siblings] or [0]) + 1
    await db.execute(text("""
        INSERT INTO carta_categories (id, company_id, parent_id, label, position)
        VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(NULLIF(:p, '') AS uuid), :label, :pos)
    """), {"id": new_id, "c": cid, "p": parent_id or "", "label": clean(label, 80).upper(), "pos": position})
    categories.append({"id": new_id, "parent_id": parent_id, "label": clean(label, 80).upper(), "position": position})
    return new_id


async def copy_media(db: AsyncSession, company_id: str, from_ref: str, to_ref: str) -> bool:
    """Lo del borrador pasa al plato real (los archivos no se copian: solo
    cambia a quien pertenecen). Lo que el plato tenia y ya no usa se borra."""
    draft = await dish_media(db, company_id, from_ref)
    if not draft or not draft.get("front_original"):
        return False
    current = await dish_media(db, company_id, to_ref) or {}
    values = {c: draft.get(c) or "" for c in MEDIA_COLUMNS}
    await upsert_media(db, company_id, to_ref, **values, use_remaster=bool(draft.get("use_remaster", True)),
                       clip_style=draft.get("clip_style"), status=draft.get("status") or "sin_video")
    await db.execute(text("""
        UPDATE menu_media_assets SET dish_ref = CAST(:to AS uuid) WHERE company_id = CAST(:c AS uuid) AND dish_ref = CAST(:fr AS uuid)
    """), {"to": to_ref, "c": company_id, "fr": from_ref})
    await db.execute(text("""
        UPDATE menu_media_jobs SET dish_ref = CAST(:to AS uuid) WHERE company_id = CAST(:c AS uuid) AND dish_ref = CAST(:fr AS uuid)
    """), {"to": to_ref, "c": company_id, "fr": from_ref})
    await db.execute(text("DELETE FROM menu_dish_media WHERE company_id = CAST(:c AS uuid) AND dish_ref = CAST(:fr AS uuid)"),
                     {"c": company_id, "fr": from_ref})
    await discard(db, company_id, [current.get(c) for c in MEDIA_COLUMNS if current.get(c) and current.get(c) not in values.values()])
    return True


async def publish(db: AsyncSession, company_id: Any, import_id: Any, table: dict) -> dict:
    """COMBINAR (sin commit): categorias que falten, platos nuevos marcados
    "receta pendiente", y precio/descripcion/foto/video de los que coinciden."""
    cid = _uuid(company_id)
    table = clean_table(table)
    plan = await plan_publish(db, cid, table)
    by_ref = {d["ref"]: d for d in table["platos"]}
    categories = await _categories(db, cid)
    for item in plan["updated"] + plan["unchanged"]:
        dish = by_ref[item["ref"]]
        await db.execute(text("""
            UPDATE carta_items SET price = COALESCE(CAST(:p AS numeric), price),
                   description = COALESCE(NULLIF(:d, ''), description), updated_at = now()
            WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)
        """), {"p": dish["precio"], "d": describe(dish), "id": item["id"], "c": cid})
        await copy_media(db, cid, dish["ref"], item["id"])
    created = []
    for item in plan["new"]:
        dish = by_ref[item["ref"]]
        top_id = await _ensure_category(db, cid, categories, dish["categoria"], None)
        leaf_id = await _ensure_category(db, cid, categories, dish["subcategoria"], top_id) if dish["subcategoria"] else top_id
        new_id = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO carta_items (id, company_id, name, presentation, price, category_key, category_id, station, requires_term,
                                     allows_portions, kind, inventory_item_id, direct_qty, active, position, description, recipe_pending)
            VALUES (CAST(:id AS uuid), CAST(:c AS uuid), :name, '', :price, :ckey, CAST(:cat AS uuid), '', false, false,
                    'preparado', NULL, 1, true,
                    (SELECT COALESCE(MAX(position), 0) + 1 FROM carta_items WHERE company_id = CAST(:c AS uuid)),
                    NULLIF(:d, ''), true)
        """), {"id": new_id, "c": cid, "name": dish["nombre"], "price": dish["precio"] or 0,
               "ckey": clean(dish["categoria"], 80).upper(), "cat": leaf_id, "d": describe(dish)})
        await copy_media(db, cid, dish["ref"], new_id)
        created.append(new_id)
    previous = ((await get_import(db, cid, import_id)) or {}).get("summary") or {}
    history = ([{k: previous.get(k) for k in ("new", "updated", "published_at")}] if previous.get("published_at") else []) + list(previous.get("history") or [])
    summary = {**plan["counts"], "new_categories": plan["new_categories"], "created_ids": created,
               "published_at": datetime.now(timezone.utc).isoformat(), "history": history[:20]}
    await db.execute(text("""
        UPDATE menu_video_imports SET status = 'publicada', summary = CAST(:s AS jsonb), published_at = now(), updated_at = now()
        WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"s": json.dumps(summary), "i": _uuid(import_id), "c": cid})
    return summary


async def dish_extras(db: AsyncSession, company_id: Any) -> dict[str, dict]:
    """description y recipe_pending de cada plato (columnas nuevas 024s)."""
    try:
        async with db.begin_nested():
            rows = (await db.execute(text("""
                SELECT id::text AS id, description, recipe_pending FROM carta_items WHERE company_id = CAST(:c AS uuid)
            """), {"c": _uuid(company_id)})).mappings().all()
    except Exception:
        return {}
    return {r["id"]: {"description": r.get("description") or "", "recipe_pending": bool(r.get("recipe_pending"))} for r in rows}


def stats_since(rows: list[dict]) -> dict:
    """Promedios de la cola (para el informe y la salud)."""
    done = [r for r in rows if r.get("status") == "listo"]
    if not done:
        return {"jobs": 0}
    def avg(key):
        values = [float(r["result"].get(key)) for r in done if isinstance(r.get("result"), dict) and r["result"].get(key) is not None]
        return round(sum(values) / len(values)) if values else None
    return {"jobs": len(done), "avg_total_ms": avg("total_ms"), "avg_clip_ms": avg("clip_ms"),
            "avg_remaster_ms": avg("front_remaster_ms"), "avg_clip_bytes": avg("clip_bytes")}


async def queue_stats(db: AsyncSession, days: int = 30) -> dict:
    rows = (await db.execute(text("""
        SELECT status, result FROM menu_media_jobs WHERE created_at > now() - make_interval(days => :d)
    """), {"d": days})).mappings().all()
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {**stats_since([{"status": r["status"], "result": _json(r["result"], {})} for r in rows]), "counts": counts}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def next_month_start(now: Optional[datetime] = None) -> datetime:
    moment = (now or utcnow()).astimezone(BOGOTA)
    first = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (first + timedelta(days=32)).replace(day=1)
