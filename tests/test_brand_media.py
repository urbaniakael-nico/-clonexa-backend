"""Fase 4 · Parte 1: imagenes de marca en el bucket.

- Solo PNG, JPG y WebP (por firma); SVG y otros se rechazan; limites de peso,
  de lado y de espacio por empresa; WebP + version liviana, sin metadatos.
- Las claves llevan el company_id; una empresa no puede leer ni borrar la
  imagen de otra; el purge borra solo las de esa empresa.
- Sin variables del bucket, el backend arranca y solo falla la subida (503 claro).
- Los endpoints exigen sesion de Admin V2.
"""
from __future__ import annotations

import io
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as app_main
from app.api.deps import get_db
from app.services import brand_media as media
from app.web import admin_v2plus_companies as ep
from app.web import brand_routes

A, B = str(uuid.uuid4()), str(uuid.uuid4())


def png(w=50, h=40, color=(200, 10, 40, 255), exif=False) -> bytes:
    img = Image.new("RGBA", (w, h), color)
    buf = io.BytesIO()
    if exif:
        img = img.convert("RGB")
        ex = Image.Exif()
        ex[0x010F] = "CamaraSecreta"
        img.save(buf, format="JPEG", exif=ex)
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()


class MemoryBucket:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key, data):
        self.objects[key] = data

    def get(self, key):
        return self.objects[key]

    def delete(self, keys):
        for k in keys:
            self.objects.pop(k, None)

    def list(self, prefix):
        return [k for k in self.objects if k.startswith(prefix)]


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def first(self):
        return self.rows[0] if self.rows else None


class ImagesDb:
    """Interpreta las pocas consultas de brand_media sobre una lista en memoria."""

    def __init__(self):
        self.images: list[dict] = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        if sql.startswith("SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes + lite_bytes)"):
            mine = [i for i in self.images if i["company_id"] == p["c"]]
            return Rows([{"n": len(mine), "used": sum(i["size_bytes"] + i["lite_bytes"] for i in mine)}])
        if sql.startswith("SELECT 1 FROM company_brand_images"):
            return Rows([1] if any(i["id"] == p["i"] and i["company_id"] == p["c"] for i in self.images) else [])
        if sql.startswith("INSERT INTO company_brand_images"):
            self.images.append({"id": p["i"], "company_id": p["c"], "size_bytes": p["s"], "lite_bytes": p["l"], "width": p["w"], "height": p["h"], "created_at": None})
            return Rows([])
        if sql.startswith("DELETE FROM company_brand_images"):
            self.images = [i for i in self.images if not (i["id"] == p["i"] and i["company_id"] == p["c"])]
            return Rows([])
        if sql.startswith("SELECT id::text AS id, size_bytes"):
            return Rows([i for i in self.images if i["company_id"] == p["c"]])
        if "FROM companies WHERE id" in sql:
            return Rows([{"id": p["id"], "name": "Empresa", "slug": "e", "status": "active", "settings_json": {}}])
        raise AssertionError(sql)

    async def commit(self):
        pass

    async def rollback(self):
        pass


@pytest.fixture
def bucket(monkeypatch):
    b = MemoryBucket()
    media.set_backend(b)
    yield b
    media.set_backend(None)


# ------------------------------------------------------------ codificar
def test_encode_png_to_webp_with_lite_and_limits():
    out = media.encode(png(3000, 1500))
    assert out.full[:4] == b"RIFF" and out.full[8:12] == b"WEBP"
    assert (out.width, out.height) == (1920, 960), "se reduce a 1920 px de lado"
    lite = Image.open(io.BytesIO(out.lite))
    assert max(lite.size) == 640
    assert len(out.lite) < len(out.full)


def test_encode_strips_metadata():
    out = media.encode(png(80, 60, exif=True))
    assert b"CamaraSecreta" not in out.full and b"CamaraSecreta" not in out.lite


@pytest.mark.parametrize("raw,msg", [
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "PNG, JPG o WebP"),
    (b"GIF89a" + b"\x00" * 50, "PNG, JPG o WebP"),
    (b"%PDF-1.4 ...", "PNG, JPG o WebP"),
    (b"\x89PNG\r\n\x1a\n" + b"basura", "No se pudo leer"),
    (b"", "vacío"),
])
def test_encode_rejects_svg_and_other_types(raw, msg):
    with pytest.raises(media.ImageRejected, match=msg):
        media.encode(raw)


def test_encode_rejects_mismatched_signature():
    # Firma de PNG pero contenido JPEG: se rechaza.
    jpeg = png(20, 20, exif=True)
    with pytest.raises(media.ImageRejected):
        media.encode(b"\x89PNG\r\n\x1a\n" + jpeg[8:])


def test_limits_are_configurable_and_bounded(monkeypatch):
    monkeypatch.setenv("CLONEXA_BRAND_MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("CLONEXA_BRAND_MAX_PX", "800")
    monkeypatch.setenv("CLONEXA_BRAND_LITE_PX", "200")
    monkeypatch.setenv("CLONEXA_BRAND_QUOTA_MB", "basura")
    lim = media.limits()
    assert (lim.max_upload_bytes, lim.max_px, lim.lite_px, lim.quota_bytes) == (1024 * 1024, 800, 200, 25 * 1024 * 1024)
    with pytest.raises(media.ImageRejected, match="más de 1 MB"):
        media.encode(b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 10))
    assert media.encode(png(2000, 1000)).width == 800


# ------------------------------------------------------------ por empresa
@pytest.mark.asyncio
async def test_upload_keys_carry_company_and_other_company_cannot_read_or_delete(bucket):
    db = ImagesDb()
    saved = await media.upload(db, A, png())
    assert set(bucket.objects) == {f"brand/{A}/{saved['id']}.webp", f"brand/{A}/{saved['id']}-lite.webp"}
    assert await media.read(db, A, saved["id"]) == bucket.objects[f"brand/{A}/{saved['id']}.webp"]
    assert await media.read(db, B, saved["id"]) is None, "otra empresa no la lee"
    assert await media.delete(db, B, saved["id"]) is False, "ni la borra"
    assert len(bucket.objects) == 2
    assert await media.list_images(db, B) == [], "ni la lista"
    with pytest.raises(media.ImageRejected):
        media.keys_for("../../otra", saved["id"])


@pytest.mark.asyncio
async def test_quota_per_company(bucket, monkeypatch):
    db = ImagesDb()
    await media.upload(db, A, png())
    used = (await media.usage(db, A))["used_bytes"]
    monkeypatch.setattr(media, "limits", lambda: media.Limits(5 * 1024 * 1024, 1920, 640, used + 10))
    with pytest.raises(media.ImageRejected, match="tope"):
        await media.upload(db, A, png())
    assert (await media.upload(db, B, png()))["id"], "el tope es por empresa"


@pytest.mark.asyncio
async def test_delete_company_only_touches_that_prefix(bucket):
    db = ImagesDb()
    await media.upload(db, A, png())
    keep = await media.upload(db, B, png())
    assert media.delete_company(A) == 2
    assert set(bucket.objects) == {f"brand/{B}/{keep['id']}.webp", f"brand/{B}/{keep['id']}-lite.webp"}


@pytest.mark.asyncio
async def test_without_bucket_variables_only_upload_fails(monkeypatch):
    media.set_backend(None)
    for k in media.REQUIRED_ENV:
        monkeypatch.delenv(media.ENV_PREFIX + k, raising=False)
    assert media.configured() is False
    with pytest.raises(media.StorageUnavailable, match="no está configurado"):
        await media.upload(ImagesDb(), A, png())
    assert media.delete_company(A) == 0, "el purge no falla sin bucket"


# ------------------------------------------------------------ rutas
@pytest.fixture
def client(monkeypatch):
    db = ImagesDb()

    async def fake_db():
        yield db

    app_main.app.dependency_overrides[get_db] = fake_db
    yield SimpleNamespace(c=TestClient(app_main.app), mp=monkeypatch, db=db)
    app_main.app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("method,path", [
    ("get", f"/admin-v2/api/brand/{A}/images"), ("post", f"/admin-v2/api/brand/{A}/images"),
    ("delete", f"/admin-v2/api/brand/{A}/images/{B}"), ("get", "/admin-v2/api/media/legacy-stats"),
])
def test_admin_endpoints_require_session(client, method, path):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    assert getattr(client.c, method)(path).status_code == 401


def test_upload_route_reports_missing_bucket_clearly(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
    media.set_backend(None)
    for k in media.REQUIRED_ENV:
        client.mp.delenv(media.ENV_PREFIX + k, raising=False)
    res = client.c.post(f"/admin-v2/api/brand/{A}/images", files={"file": ("logo.png", png(), "image/png")})
    assert res.status_code == 503 and "no está configurado" in res.json()["detail"]


def test_upload_and_serve_same_origin(client, bucket):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
    client.mp.setattr(brand_routes.v2, "_active_session", AsyncMock(return_value=True))
    res = client.c.post(f"/admin-v2/api/brand/{A}/images", files={"file": ("x.svg", b"<svg/>", "image/svg+xml")})
    assert res.status_code == 422
    res = client.c.post(f"/admin-v2/api/brand/{A}/images", files={"file": ("logo.png", png(), "image/png")})
    assert res.status_code == 200
    url = res.json()["image"]["url"]
    got = client.c.get(url)
    assert got.status_code == 200 and got.headers["content-type"] == "image/webp"
    assert "max-age" in got.headers["cache-control"] and got.headers["x-content-type-options"] == "nosniff"
    assert client.c.get(url.replace(".webp", "-lite.webp")).status_code == 200
    assert client.c.get(url.replace(A, B)).status_code == 404, "la imagen de A no se sirve como de B"
    client.mp.setattr(brand_routes.v2, "_active_session", AsyncMock(return_value=False))
    assert client.c.get(url).status_code == 404, "sin permiso no se ve"
    assert client.c.get(f"/brand-media/{A}/..%2Fsecreto.webp").status_code == 404


@pytest.mark.asyncio
async def test_legacy_stats_counts_without_moving_anything():
    calls = []

    class Db:
        async def execute(self, statement, params=None):
            sql = " ".join(str(statement).split())
            calls.append(sql)
            if "information_schema.columns" in sql:
                return Rows([{"table_name": "hospitality_categories", "column_name": "image_bytes"},
                             {"table_name": "hospitality_product_images", "column_name": "image_bytes"}])
            if 'FROM "hospitality_categories"' in sql:
                return Rows([{"n": 12, "bytes": 1_200_000, "companies": 2}])
            if 'FROM "hospitality_product_images"' in sql:
                return Rows([{"n": 30, "bytes": 3_000_000, "companies": 1}])
            if "logo LIKE 'data:image/%'" in sql:
                return Rows([{"n": 2, "bytes": 400_000}])
            raise AssertionError(sql)

    data = await brand_routes.legacy_stats(Db())
    assert data["total_images"] == 44 and data["total_bytes"] == 4_600_000
    assert not any(s.split()[0].upper() in {"UPDATE", "DELETE", "INSERT"} for s in calls), "solo lee"
