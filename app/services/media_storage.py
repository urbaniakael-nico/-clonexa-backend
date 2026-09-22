"""Single seam between "where do we keep an uploaded image" and everything
that uploads or serves one.

Today it's bytes in Postgres, capped and resized (the database has 500MB
total and ~235MB was already in use as of 2026-09-23 -- see CLAUDE.md). If
this moves to a Railway bucket later, only this file changes: no endpoint,
no frontend call site, and no other module needs to know where the bytes
actually live.

Every caller works against a company-scoped table that already has
`image_bytes BYTEA` and `image_content_type VARCHAR` columns (and a unique
constraint on whatever key_columns identify a row) -- this module never
creates or alters that table itself, it only ever UPDATEs the image pair on
a row the caller already made sure exists.
"""
from __future__ import annotations

import io
import re

from fastapi import HTTPException, status
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MAX_IMAGE_BYTES = 200 * 1024  # 200 KB -- keeps the whole catalog a few MB, see CLAUDE.md
MAX_IMAGE_WIDTH = 800  # px, plenty for a phone screen
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
_TABLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_COLUMN_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _assert_safe_identifier(value: str, pattern: re.Pattern[str], kind: str) -> str:
    if not pattern.match(value):
        raise ValueError(f"Unsafe {kind} identifier: {value!r}")
    return value


def _resize_and_encode(raw: bytes, content_type: str) -> tuple[bytes, str]:
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se pudo leer la imagen.")

    if image.width > MAX_IMAGE_WIDTH:
        ratio = MAX_IMAGE_WIDTH / float(image.width)
        target_height = max(1, round(image.height * ratio))
        image = image.resize((MAX_IMAGE_WIDTH, target_height), Image.LANCZOS)

    save_format = "PNG" if content_type == "image/png" else "JPEG"
    if save_format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    buffer = io.BytesIO()
    if save_format == "JPEG":
        image.save(buffer, format="JPEG", quality=85, optimize=True)
    else:
        image.save(buffer, format="PNG", optimize=True)
    encoded = buffer.getvalue()

    if len(encoded) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"La imagen sigue pesando mas de {MAX_IMAGE_BYTES // 1024} KB incluso redimensionada. "
                "Usa una mas liviana."
            ),
        )
    return encoded, f"image/{save_format.lower()}"


async def save_image(
    db: AsyncSession,
    *,
    table: str,
    key_columns: dict[str, object],
    raw: bytes,
    content_type: str,
) -> None:
    """Resize/validate `raw`, then replace the image on the row matched by
    `key_columns` (an UPDATE, never an INSERT of a new image row) -- so a new
    photo always replaces the old one, never accumulates alongside it. The
    row itself (and any of its non-image columns) must already exist;
    callers own creating/upserting that separately."""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Formato de imagen no soportado (usa PNG, JPG o WEBP).",
        )
    if not raw:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="imagen_vacia")

    _assert_safe_identifier(table, _TABLE_NAME_RE, "table")
    for column in key_columns:
        _assert_safe_identifier(column, _COLUMN_NAME_RE, "column")

    encoded, final_content_type = _resize_and_encode(raw, content_type)

    where_clause = " AND ".join(f"{column} = :{column}" for column in key_columns)
    await db.execute(
        text(
            f"""
            UPDATE {table}
            SET image_bytes = :image_bytes,
                image_content_type = :image_content_type,
                updated_at = NOW()
            WHERE {where_clause}
            """
        ),
        {**key_columns, "image_bytes": encoded, "image_content_type": final_content_type},
    )


async def get_image(
    db: AsyncSession,
    *,
    table: str,
    key_columns: dict[str, object],
) -> tuple[bytes, str] | None:
    _assert_safe_identifier(table, _TABLE_NAME_RE, "table")
    for column in key_columns:
        _assert_safe_identifier(column, _COLUMN_NAME_RE, "column")

    where_clause = " AND ".join(f"{column} = :{column}" for column in key_columns)
    result = await db.execute(
        text(f"SELECT image_bytes, image_content_type FROM {table} WHERE {where_clause} LIMIT 1"),
        key_columns,
    )
    row = result.mappings().first()
    if not row or not row["image_bytes"]:
        return None
    return bytes(row["image_bytes"]), row["image_content_type"] or "image/png"


async def delete_image(
    db: AsyncSession,
    *,
    table: str,
    key_columns: dict[str, object],
) -> None:
    _assert_safe_identifier(table, _TABLE_NAME_RE, "table")
    for column in key_columns:
        _assert_safe_identifier(column, _COLUMN_NAME_RE, "column")

    where_clause = " AND ".join(f"{column} = :{column}" for column in key_columns)
    await db.execute(
        text(
            f"""
            UPDATE {table}
            SET image_bytes = NULL, image_content_type = NULL, updated_at = NOW()
            WHERE {where_clause}
            """
        ),
        key_columns,
    )
