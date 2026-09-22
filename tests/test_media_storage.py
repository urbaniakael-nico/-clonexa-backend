"""media_storage.py is the single seam between "where do we keep an image"
and everything that uploads/serves one (see its own module docstring and
CLAUDE.md's database-space rule). These tests pin: rejection of unsupported
formats/empty uploads, the 200KB-after-resize rejection with a clear message,
that a save is always a replace (UPDATE) never an accumulate (INSERT), and
that a row with no image returns None instead of an error.
"""
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
from PIL import Image
import pytest

from app.services import media_storage


def _png_bytes(width, height, color=(200, 60, 120)):
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


@pytest.mark.asyncio
async def test_save_image_rejects_unsupported_content_type():
    db = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await media_storage.save_image(
            db, table="hospitality_categories", key_columns={"id": "x"},
            raw=b"whatever", content_type="application/pdf",
        )
    assert exc.value.status_code == 422
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_image_rejects_empty_upload():
    db = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await media_storage.save_image(
            db, table="hospitality_categories", key_columns={"id": "x"},
            raw=b"", content_type="image/png",
        )
    assert exc.value.status_code == 422
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_image_resizes_wide_images_and_replaces_never_accumulates():
    db = SimpleNamespace(execute=AsyncMock())
    raw = _png_bytes(1600, 800)

    await media_storage.save_image(
        db, table="hospitality_categories", key_columns={"company_id": "c1", "category_key": "cerveza"},
        raw=raw, content_type="image/png",
    )

    db.execute.assert_awaited_once()
    statement, params = db.execute.await_args.args
    text = str(statement)
    assert "UPDATE hospitality_categories" in text
    assert "INSERT" not in text
    assert params["company_id"] == "c1"
    assert params["category_key"] == "cerveza"
    assert len(params["image_bytes"]) <= media_storage.MAX_IMAGE_BYTES


@pytest.mark.asyncio
async def test_save_image_rejects_with_clear_message_when_still_over_cap_after_resize(monkeypatch):
    monkeypatch.setattr(media_storage, "MAX_IMAGE_BYTES", 10)
    db = SimpleNamespace(execute=AsyncMock())
    raw = _png_bytes(200, 200)

    with pytest.raises(HTTPException) as exc:
        await media_storage.save_image(
            db, table="hospitality_categories", key_columns={"id": "x"},
            raw=raw, content_type="image/png",
        )

    assert exc.value.status_code == 422
    assert "KB" in exc.value.detail
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_image_returns_none_when_row_has_no_image():
    db = SimpleNamespace(execute=AsyncMock(return_value=FakeResult({"image_bytes": None, "image_content_type": None})))

    result = await media_storage.get_image(db, table="hospitality_categories", key_columns={"id": "x"})

    assert result is None


@pytest.mark.asyncio
async def test_get_image_returns_bytes_and_content_type_when_present():
    db = SimpleNamespace(execute=AsyncMock(return_value=FakeResult({"image_bytes": b"\x89PNG", "image_content_type": "image/png"})))

    result = await media_storage.get_image(db, table="hospitality_categories", key_columns={"id": "x"})

    assert result == (b"\x89PNG", "image/png")


@pytest.mark.asyncio
async def test_delete_image_clears_both_columns_without_dropping_the_row():
    db = SimpleNamespace(execute=AsyncMock())

    await media_storage.delete_image(db, table="hospitality_categories", key_columns={"id": "x"})

    db.execute.assert_awaited_once()
    statement, _params = db.execute.await_args.args
    text = str(statement)
    assert "UPDATE hospitality_categories" in text
    assert "image_bytes = NULL" in text
