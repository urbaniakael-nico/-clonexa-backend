"""Versiones de la marca por empresa: borrador, publicacion e historial.

- Editar solo cambia el borrador; lo que ven los operarios es la version
  publicada (published_tokens). Publicar y volver de version son explicitos.
- Toda consulta filtra por company_id. Las imagenes de los tokens deben ser
  de ESA empresa (company_brand_images); copiar de otra empresa nunca lleva
  sus imagenes.
- Maximo 10 versiones por empresa: se borran las archivadas mas viejas.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import brand_media as media
from app.services import brand_theme as bt

log = logging.getLogger("clonexa.brand")


class BrandConflict(Exception):
    """Accion imposible en el estado actual (p. ej. publicar sin borrador)."""


def _row(r: Any) -> dict:
    tokens = r["tokens"]
    if isinstance(tokens, str):
        tokens = json.loads(tokens)
    return {"version": int(r["version"]), "status": r["status"], "tokens": tokens,
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "published_at": r["published_at"].isoformat() if r.get("published_at") else None}


async def _rows(db: AsyncSession, cid: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT version, status, tokens, created_at, published_at FROM company_brand_themes
        WHERE company_id = CAST(:c AS uuid) ORDER BY version DESC
    """), {"c": cid})).mappings().all()
    return [_row(r) for r in rows]


async def check_images(db: AsyncSession, cid: str, tokens: dict) -> None:
    ids = bt.image_ids(tokens)
    if not ids:
        return
    owned = {str(r[0]) for r in (await db.execute(text("""
        SELECT id::text FROM company_brand_images WHERE company_id = CAST(:c AS uuid) AND id::text = ANY(:ids)
    """), {"c": cid, "ids": sorted(ids)})).all()}
    missing = ids - owned
    if missing:
        raise bt.BrandInvalid("imagen", "una imagen no es de esta empresa o ya no existe")


async def _next_version(db: AsyncSession, cid: str) -> int:
    return int((await db.execute(text("SELECT COALESCE(MAX(version), 0) + 1 FROM company_brand_themes WHERE company_id = CAST(:c AS uuid)"),
                                 {"c": cid})).scalar() or 1)


async def _insert(db: AsyncSession, cid: str, status: str, tokens: dict) -> int:
    version = await _next_version(db, cid)
    await db.execute(text("""
        INSERT INTO company_brand_themes (company_id, version, status, tokens, published_at)
        VALUES (CAST(:c AS uuid), :v, CAST(:s AS varchar), CAST(:t AS jsonb), CASE WHEN CAST(:s AS varchar) = 'published' THEN now() ELSE NULL END)
    """), {"c": cid, "v": version, "s": status, "t": json.dumps(tokens, ensure_ascii=False)})
    return version


async def _prune(db: AsyncSession, cid: str) -> None:
    await db.execute(text("""
        DELETE FROM company_brand_themes WHERE company_id = CAST(:c AS uuid) AND status = 'archived' AND version NOT IN (
            SELECT version FROM company_brand_themes WHERE company_id = CAST(:c AS uuid) ORDER BY version DESC LIMIT :keep)
    """), {"c": cid, "keep": bt.MAX_VERSIONS})


async def _initial_logo(db: AsyncSession, cid: str, branding: dict) -> Optional[str]:
    """El logo de company_branding (data:image) pasa al bucket. Si no se puede, sin logo."""
    logo = str(branding.get("logo_url") or "")
    if not logo.startswith("data:image/") or ";base64," not in logo or not media.configured():
        return None
    try:
        raw = base64.b64decode(logo.split(";base64,", 1)[1], validate=False)
        return (await media.upload(db, cid, raw))["id"]
    except Exception as error:  # el estudio abre igual, sin logo
        log.warning("marca: no se pudo pasar el logo al bucket company=%s: %s", cid, type(error).__name__)
        return None


async def _edited(db: AsyncSession, cid: str) -> bool:
    """Si alguien edito la marca de esta empresa (la auditoria guarda cada
    guardado, publicacion, copia o vuelta de version). Sin auditoria: se asume
    que si, para no tocar nada."""
    try:
        row = (await db.execute(text("""
            SELECT 1 FROM admin_audit_log
            WHERE path LIKE :p AND method IN ('PUT', 'POST')
              AND (path LIKE '%/draft' OR path LIKE '%/publish' OR path LIKE '%/rollback/%' OR path LIKE '%/copy-from/%' OR path LIKE '%/unpublish')
            LIMIT 1
        """), {"p": f"/admin-v2/api/brand/{cid}/%"})).first()
    except Exception:
        await db.rollback()
        return True
    return row is not None


def _old_initial(row: dict) -> bool:
    """Borrador armado con la logica anterior a la etapa 2 (sin theme.portal)."""
    theme = (row.get("tokens") or {}).get("theme") or {}
    return "portal" not in theme


async def state(db: AsyncSession, cid: str, branding: dict, panels: bool = False) -> dict:
    """Borrador, publicado e historial. La primera vez arma el borrador desde
    company_branding (la marca de Admin V2), logo incluido, de forma que
    publicado sin cambios se vea como hoy. Un borrador inicial creado con la
    logica anterior y que nadie edito se regenera (conserva su logo)."""
    rows = await _rows(db, cid)
    if not rows:
        logo = await _initial_logo(db, cid, branding)
        await _insert(db, cid, "draft", bt.from_branding(branding, logo, panels=panels))
        await db.commit()
        rows = await _rows(db, cid)
    elif len(rows) == 1 and rows[0]["status"] == "draft" and rows[0]["version"] == 1 and _old_initial(rows[0]) and not await _edited(db, cid):
        logo = ((rows[0]["tokens"].get("theme") or {}).get("logo")) or None
        fresh = bt.from_branding(branding, logo, panels=panels)
        await db.execute(text("""
            UPDATE company_brand_themes SET tokens = CAST(:t AS jsonb) WHERE company_id = CAST(:c AS uuid) AND status = 'draft' AND version = 1
        """), {"c": cid, "t": json.dumps(fresh, ensure_ascii=False)})
        await db.commit()
        log.info("marca: borrador inicial regenerado con la logica nueva company=%s", cid)
        rows = await _rows(db, cid)
    draft = next((r for r in rows if r["status"] == "draft"), None)
    published = next((r for r in rows if r["status"] == "published"), None)
    if draft is None:
        base = published["tokens"] if published else bt.from_branding(branding, panels=panels)
        await _insert(db, cid, "draft", base)
        await _prune(db, cid)
        await db.commit()
        rows = await _rows(db, cid)
        draft = next(r for r in rows if r["status"] == "draft")
    # Lo guardado se entrega validado (completa los campos nuevos de la etapa 2).
    for r in (draft, published):
        if r:
            try:
                r["tokens"] = bt.validate(r["tokens"])
            except bt.BrandInvalid:
                pass
    history = [{k: r[k] for k in ("version", "status", "created_at", "published_at")} for r in rows]
    return {"draft": draft, "published": published, "history": history}


async def save_draft(db: AsyncSession, cid: str, tokens: Any) -> dict:
    clean = bt.validate(tokens)
    await check_images(db, cid, clean)
    updated = (await db.execute(text("""
        UPDATE company_brand_themes SET tokens = CAST(:t AS jsonb), created_at = now()
        WHERE company_id = CAST(:c AS uuid) AND status = 'draft'
    """), {"c": cid, "t": json.dumps(clean, ensure_ascii=False)})).rowcount
    if not updated:
        await _insert(db, cid, "draft", clean)
        await _prune(db, cid)
    await db.commit()
    return clean


async def publish(db: AsyncSession, cid: str) -> int:
    row = (await db.execute(text("""
        SELECT version, tokens FROM company_brand_themes WHERE company_id = CAST(:c AS uuid) AND status = 'draft'
    """), {"c": cid})).mappings().first()
    if not row:
        raise BrandConflict("No hay borrador para publicar.")
    tokens = row["tokens"] if isinstance(row["tokens"], dict) else json.loads(row["tokens"])
    clean = bt.validate(tokens)
    await check_images(db, cid, clean)
    await db.execute(text("UPDATE company_brand_themes SET status = 'archived' WHERE company_id = CAST(:c AS uuid) AND status = 'published'"), {"c": cid})
    await db.execute(text("""
        UPDATE company_brand_themes SET status = 'published', published_at = now()
        WHERE company_id = CAST(:c AS uuid) AND version = :v
    """), {"c": cid, "v": int(row["version"])})
    await _prune(db, cid)
    await db.commit()
    return int(row["version"])


async def rollback(db: AsyncSession, cid: str, version: int) -> int:
    row = (await db.execute(text("""
        SELECT version, status, tokens FROM company_brand_themes WHERE company_id = CAST(:c AS uuid) AND version = :v
    """), {"c": cid, "v": int(version)})).mappings().first()
    if not row or row["status"] != "archived":
        raise BrandConflict("Esa versión no existe o no es una versión anterior.")
    tokens = row["tokens"] if isinstance(row["tokens"], dict) else json.loads(row["tokens"])
    await check_images(db, cid, bt.validate(tokens))
    await db.execute(text("UPDATE company_brand_themes SET status = 'archived' WHERE company_id = CAST(:c AS uuid) AND status = 'published'"), {"c": cid})
    await db.execute(text("""
        UPDATE company_brand_themes SET status = 'published', published_at = now()
        WHERE company_id = CAST(:c AS uuid) AND version = :v
    """), {"c": cid, "v": int(version)})
    await db.commit()
    return int(version)


async def unpublish(db: AsyncSession, cid: str) -> None:
    """Vuelve a la marca de siempre (company_branding): archiva la publicada."""
    await db.execute(text("UPDATE company_brand_themes SET status = 'archived' WHERE company_id = CAST(:c AS uuid) AND status = 'published'"), {"c": cid})
    await db.commit()


async def tokens_for_copy(db: AsyncSession, source_cid: str) -> Optional[dict]:
    """Tokens de otra empresa SIN sus imagenes (publicado, o si no su borrador)."""
    row = (await db.execute(text("""
        SELECT tokens FROM company_brand_themes WHERE company_id = CAST(:c AS uuid) AND status IN ('published', 'draft')
        ORDER BY CASE status WHEN 'published' THEN 0 ELSE 1 END LIMIT 1
    """), {"c": source_cid})).mappings().first()
    if not row:
        return None
    tokens = row["tokens"] if isinstance(row["tokens"], dict) else json.loads(row["tokens"])
    return bt.without_images(bt.validate(tokens))


async def published_tokens(db: AsyncSession, cid: str) -> Optional[dict]:
    """La marca publicada de ESA empresa, o None (se ve igual que hoy)."""
    try:
        row = (await db.execute(text("""
            SELECT tokens FROM company_brand_themes WHERE company_id = CAST(:c AS uuid) AND status = 'published' LIMIT 1
        """), {"c": cid})).mappings().first()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        return None
    if not row:
        return None
    tokens = row["tokens"] if isinstance(row["tokens"], dict) else json.loads(row["tokens"])
    try:
        return bt.validate(tokens)
    except bt.BrandInvalid:
        log.warning("marca publicada invalida company=%s; se sirve la de siempre", cid)
        return None


async def draft_tokens(db: AsyncSession, cid: str) -> Optional[dict]:
    """El borrador guardado de ESA empresa (sin crearlo), o None."""
    row = (await db.execute(text("""
        SELECT tokens FROM company_brand_themes WHERE company_id = CAST(:c AS uuid) AND status = 'draft' LIMIT 1
    """), {"c": cid})).mappings().first()
    if not row:
        return None
    tokens = row["tokens"] if isinstance(row["tokens"], dict) else json.loads(row["tokens"])
    try:
        return bt.validate(tokens)
    except bt.BrandInvalid:
        return None
